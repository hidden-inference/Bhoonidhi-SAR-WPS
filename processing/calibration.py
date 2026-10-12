import numpy as np


def gamma0_linear(dn, calibration_db, noise_bias, valid=None):
    # gamma0 = (DN^2 - noise_bias) / 10^(K/10), EOS-04 format document section 6.3
    if not np.isfinite([calibration_db, noise_bias]).all() or noise_bias < 0:
        raise ValueError('Invalid calibration constant or noise bias')
    dn = np.asarray(dn, dtype=np.float64)
    power = dn**2 - noise_bias
    base = np.isfinite(dn) & (dn > 0)
    if valid is not None:
        base &= valid
    good = base & (power > 0)
    scale = 10.0 ** (calibration_db / 10.0)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError('Calibration scale out of range')
    out = np.full(dn.shape, np.nan)
    out[good] = power[good] / scale
    return out, base & (power <= 0)


def to_db(intensity):
    a = np.asarray(intensity, dtype=np.float64)
    out = np.full(a.shape, np.nan)
    valid = np.isfinite(a) & (a > 0)
    out[valid] = 10 * np.log10(a[valid])
    return out
