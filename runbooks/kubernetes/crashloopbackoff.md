# Kubernetes — CrashLoopBackOff

## Overview

A pod in `CrashLoopBackOff` is repeatedly starting, crashing, and being restarted by kubelet. Each restart cycle backs off exponentially (10 s → 20 s → 40 s → 80 s → 160 s → 300 s cap). The pod will never recover on its own if the root cause is not fixed.

**Common causes:**
- Application error on startup (bad config, missing env var, failed migration)
- OOMKilled — container exceeds its memory limit
- Liveness probe failing immediately after start
- Missing or invalid secret / ConfigMap mount
- Image pull succeeded but entrypoint command is wrong

## Diagnosis

### 1. Identify the failing pod

```bash
kubectl get pods -n <namespace> --field-selector=status.phase!=Running
kubectl get pods -n <namespace> | grep CrashLoop
```

### 2. Check recent exit code and reason

```bash
kubectl describe pod <pod-name> -n <namespace>
```

Look for `Last State` → `Exit Code`. Common codes:

| Exit Code | Meaning |
|-----------|---------|
| 1 | Application error — check logs |
| 137 | OOMKilled (SIGKILL from kernel) |
| 139 | Segfault |
| 143 | SIGTERM — graceful shutdown requested |

### 3. Read the logs

```bash
# Current (possibly empty if crashed immediately)
kubectl logs <pod-name> -n <namespace>

# Previous crash logs — always check this first
kubectl logs <pod-name> -n <namespace> --previous
```

### 4. Check resource pressure

```bash
kubectl top pod <pod-name> -n <namespace>
kubectl describe node <node-name> | grep -A5 "Allocated resources"
```

### 5. Inspect environment and mounts

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml | grep -A20 env:
kubectl exec -it <pod-name> -n <namespace> -- env | sort
```

## Common Fixes

### OOMKilled (Exit Code 137)

Increase the container memory limit in the Deployment spec:

```yaml
resources:
  requests:
    memory: "256Mi"
  limits:
    memory: "512Mi"
```

Apply: `kubectl apply -f deployment.yaml`

Do not remove limits — set them high enough. Removing them risks noisy-neighbour evictions on the node.

### Missing environment variable

The app logs will typically show `KeyError`, `RuntimeError`, or similar. Verify the ConfigMap or Secret exists:

```bash
kubectl get configmap <name> -n <namespace>
kubectl get secret <name> -n <namespace>
```

If missing, create from the values in Parameter Store or Secrets Manager and patch the deployment.

### Liveness probe too aggressive

If the probe fires before the app is ready:

```yaml
livenessProbe:
  initialDelaySeconds: 30   # increase from default
  periodSeconds: 10
  failureThreshold: 3
```

### Bad image entrypoint

```bash
kubectl run debug --image=<your-image> --restart=Never --rm -it -- /bin/sh
```

Confirm the binary exists and the command is correct.

## Escalation

If the pod is still crash-looping after applying fixes, check:
1. Events on the namespace: `kubectl get events -n <namespace> --sort-by='.lastTimestamp'`
2. Node conditions: `kubectl describe node <node-name> | grep -A10 Conditions`
3. Whether the issue is isolated to one node (cordon it and force a reschedule)

## Related Runbooks

- `runbooks/kubernetes/oomkilled.md`
- `runbooks/kubernetes/pending-pods.md`
