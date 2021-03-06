"""Compute optical airglow emission and transmission.

Refer to Section 4 of Nolll 2012 for details.
"""
import numpy as np

import skysim.utils.data
import skysim.utils.resample
import skysim.transmission


def airmass_ag(z):
    """Calculate the effective airmass of airglow emission from ~90km.

    Use equation (23) of Noll 2012.

    Parameters
    ----------
    z : float or array
        Zenith angle(s) in degrees.

    Returns
    -------
    float or array
        Airmass(es) corresponding to each input zenith angle.
    """
    z = np.asarray(z)
    return (1 - 0.972 * np.sin(np.deg2rad(z)) ** 2) ** -0.5


def airglow_scattering(z):
    """Calculate net Rayleigh and Mie scattering of airglow emission.

    Use equations (24) and (25) of Noll 2012 to approximate the
    net effect of scattering as an optical depth multiplier.
    Negative values are possible and indicate that scattering
    of indirect airglow into the line of sight exceeds scattering
    of direct airglow out of the line of sight.

    Parameters
    ----------
    z : float or array
        Zenith angle(s) in degrees.

    Returns
    -------
    tuple
        Tuple (fR, fM) giving the net optical depth multipliers for
        Rayleigh and Mie scattering, respectively.  The components
        fR, fM will be floats or arrays matching the input z shape.
    """
    x = np.log10(airmass_ag(z))
    # Calculate the Rayleigh scattering fraction.
    fR = 1.669 * x - 0.146
    fM = 1.732 * x - 0.318
    return fR, fM


def get_airglow(lam, z, p=744., H=2.64,
                Rayleigh=True, Mie=True, absorption=True):
    """Calculate airglow flux.

    Automatically broadcasts over input arrays, but the wavelength
    input ``lam`` must be 1D and appear in the last axis.

    The CPU time scales with the number of unique values in ``z``
    so calculating on a grid with many duplicates of the same
    value is relatively efficient (e.g., :class:`skysim.utils.AltAzGrid`).

    Parameters
    ----------
    lam : float or 1D array
        Wavelength in nanometers.
    z : float or array
        Zenith angle(s) in degrees.
    p : float or array
        Pressure at the observation elevation in hPa, used for Rayleigh
        scattering.
    H : float or array
        Elevation of the observation in km, used for Rayleigh scattering.
    Rayleigh : bool
        Apply Rayleigh scattering effects.
    Mie : bool
        Apply aerosol Mie scattering effects.
    absorption : bool
        Apply molecular (but not ozone) absorption effects.

    Returns
    -------
    tuple
        Tuple (cont, line) of arrays of airglow continuum and line fluxes in
        ph / (s cm2 nm).
    """
    lam = np.atleast_1d(lam)
    z = np.asarray(z)
    z_unique = np.unique(z)
    if 4 * z_unique.size < 3 * z.size:
        # Only do the calculation for unique values of z, remembering how
        # to assemble the output array.
        z_compressed = True
        assert z.shape[-1] == 1
        idx_out = np.searchsorted(z_unique, np.squeeze(z, -1))
        z = z_unique.reshape(-1, 1)
    else:
        z_compressed = False
    # Lookup the unextincted airglow fluxes.
    atm = skysim.utils.data.get('atmosphere')
    cont = atm['airglow_cont'].data.copy()
    line = atm['airglow_line'].data.copy()
    # Apply absorption on the high-resolution atmosphere table grid.
    Xag = airmass_ag(z)
    if absorption:
        transmission = atm['trans_ma'].data ** Xag
        cont = cont * transmission
        line = line * transmission
    # Resample to output wavelength grid for scattering calculations.
    ag_lam = atm['wavelength'].data.copy()
    cont = skysim.utils.resample.resample_density(lam, ag_lam, cont)
    line = skysim.utils.resample.resample_density(lam, ag_lam, line)
    # Apply scattering effects.
    if Rayleigh or Mie:
        fR, fM = airglow_scattering(z)
        tau0 = np.zeros_like(cont)
        if Rayleigh:
            tau0 += fR * skysim.transmission.tau0R(lam, p, H)
        if Mie:
            tau0 += fM * skysim.transmission.tau0M(lam)
        scattering = np.exp(-tau0 * Xag)
        cont = cont * scattering
        line = line * scattering

    if z_compressed:
        # Assemble the ouput, repeating values with the same z as necessary.
        cont = cont[idx_out]
        line = line[idx_out]

    return cont, line
