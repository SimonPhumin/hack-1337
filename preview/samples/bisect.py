def bisect(xs: list[float], target: float, eps: float = 1e-9) -> int | None:
    """Index of `target` in the sorted list `xs`, or None if it isn't there."""
    if (n := len(xs)) == 0:
        return None
    lo, hi = 0, n - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if abs(xs[mid] - target) < eps:
            return mid
        elif xs[mid] >= target:  # target is to the left
            hi = mid - 1
        else:
            lo = mid + 1
    return None
