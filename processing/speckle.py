import numpy as np
from scipy.ndimage import convolve


def lee3x3(intensity, enl, min_neighbors=1):
    if not np.isfinite(enl) or enl <= 0:
        raise ValueError('ENL must be finite and positive')
    if min_neighbors not in range(1, 10):
        raise ValueError('min_neighbors must be 1..9')
    a = np.asarray(intensity, dtype=np.float64)
    valid = np.isfinite(a) & (a > 0)
    values = np.where(valid, a, 0)
    def sums(v):
        return convolve(v, np.ones((3,3)), mode='constant', cval=0)
    count = sums(valid.astype(float))
    mean = sums(values) / np.maximum(count, 1)
    var = np.maximum(sums(values**2) / np.maximum(count,1) - mean**2, 0)
    signal_var = np.maximum((var - mean**2/enl)/(1+1/enl), 0)
    weight = np.divide(signal_var, var, out=np.zeros_like(var), where=var>0)
    out = mean + np.clip(weight,0,1)*(values-mean)
    out[~valid | (count < min_neighbors)] = np.nan
    return out


def statistics(a):
    values = np.asarray(a)[np.isfinite(a) & (np.asarray(a)>0)]
    if not values.size:
        return dict(count=0, mean=None, variance=None, enl=None)
    mean, var = float(values.mean()), float(values.var())
    return dict(count=int(values.size), mean=mean, variance=var, enl=mean*mean/var if var else None)
