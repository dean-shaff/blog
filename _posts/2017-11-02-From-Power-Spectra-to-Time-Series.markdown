---
layout: post
title:  "From Power Spectra to Time Series"
date:   2017-11-02 10:31:00 +0400
categories: fourier, power spectra
---
In the radio astronomy work I do, much of the data I interact with are spectra.
A power spectrum shows power as a function of frequency. Power spectra are
useful for two reasons: One, the integral of the power spectrum is equal to the
total energy of the signal we originally receive. See Parseval's theorem Two,
the power spectrum shows spectral line emission information. These spectral
lines contain information about the chemical constituents of the sources we
look. It has been quite a while since I've formally studied how emission works,
but in short, chemicals get energetically excited and emit radiation as a means
of dissipating that energy. The emitted radiation is specific to the electron
transitions happening in the molecule, so spectral lines can be used to
identify which molecules are present in a source. Power spectra can also
illuminate interesting physics happening at the source. For instance, we can
infer the presence of rotating material in a source, by looking at small red
and blue shifts of a particular line. This is particularly  meaningful if a
source cannot be resolved (it appears as a point source); we are gaining
information about the physics of material in the source without being able to
take a detailed picture.


I usually spend much of my time looking at power spectra. Once a particular
dataset is calibrated, it is pretty clear whether particular spectra lines are
present or not; they appear as narrow bumps in the power spectrum at an
expected frequency. Sometime this summer, I asked myself whether or not we
could listen for these frequency domain bumps. Translating from the frequency
domain to the time domain is pretty easy, as illustrated with this little
snippet of Python/Numpy code:


{% highlight python %}

import numpy as np

def generate_time_series(power_spectrum):
    """
    Generate time series data from a given power spectrum, or
    stack of power spectra.
    Args:
        power_spectrum (np.ndarray): The power spectrum, or power spectra
            for which we want to compute time series data.
    Returns
        np.ndarray
    """
    mag = np.absolute(power_spectrum)

    min_phase, max_phase = -np.pi, np.pi

    phase = np.random.uniform(min_phase, max_phase, size=power_spectrum.shape[1])
    phase_tiled = np.tile(phase, (power_spectrum.shape[0],1))

    FFT = mag * np.exp(1j*phase_tiled)

    iFFT = np.fft.ifft(FFT, axis=1)

    time_series = iFFT.flatten()

    return time_series
    
{% endhighlight %}
