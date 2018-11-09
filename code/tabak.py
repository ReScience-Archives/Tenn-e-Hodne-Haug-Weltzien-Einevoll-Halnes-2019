from __future__ import absolute_import, division, print_function, unicode_literals

import numpy as np

import neuron
nrn = neuron.h

# time step
# This can be changed to dt = 0.25 to speed up the model,
# without large qualitative changes in the results
dt = 0.01 # ms

A = 3.1415927e-6 # cm^2

def scale_conductance(G_x):
    """
    Rescale the conductances from from Tabak et. al. 2011 (nS) to the conductances
    required by neuron (S/cm^2).

    Parameters
    ----------
    G_x : {float, int}
        Conductance from Tabak et. al. 2011 in nS.

    Returns
    -------
    g_x_NEURON : {float, int}
        Conductance scaled to what neuron requires (S/cm^2). The cell has an area
        of 3.1415927e-6 cm^2.

    Notes
    -----
    Area of neuron cell: 3.1415927e-6 cm^2
    """
    g_x_NEURON = G_x*1e-9/A

    return g_x_NEURON


c = 10*1e-6/A
alpha = 0.0015*A*10**6

g_l_scaled = scale_conductance(0.2)
g_K_scaled = scale_conductance(3)
g_Ca_scaled = scale_conductance(2)
g_SK_scaled = scale_conductance(2)


def create_soma(g_l=g_l_scaled,
                e_pas=-50,
                g_K=g_K_scaled,
                g_Ca=g_Ca_scaled,
                g_SK=g_SK_scaled,
                g_BK=0,
                tau_BK=5):
    """
    Create the soma of a neuron.

    Parameters
    ----------
    g_l : float, optional
        The leak conductance, in S/cm^2. Default is 6.37e-5 S/cm^2.
    e_pas : float, optional
        Reversal potential for the leak current, in mV. Default is -50 mV.
    g_K : float, optional
        The maximal conductance of K channels, in S/cm^2. Default is
        9.55e-4 S/cm^2.
    g_Ca : float, optional
        The maximal conductance of Ca channels, in S/cm^2. Default is
        6.37e-4 S/cm^2.
    g_SK : float, optional
        The maximal conductance of SK channels, in S/cm^2. Default is
        6.37e-4 S/cm^2.
    g_BK : float, optional
        The maximal conductance of BK channels, in S/cm^2. Default is 0 S/cm^2.
    tau_BK : float, optional
        Time constant of the BK channel, in ms. Default is 5 ms.

    Returns
    -------
    soma : soma NEURON object
        The soma NEURON object.
    """
    nrn('forall delete_section()')
    soma = nrn.Section('soma')
    soma.L = 10                            # um; stored as a float number
    soma.diam = 10                         # um
    soma.nseg = 1                          # stored as an integer

    for sec in nrn.allsec():
        sec.insert('pas')
        sec.Ra = 100
        sec.cm = c
        sec.insert("kdrt")                 # From Tabak 2011
        sec.insert("Cadt")                 # From Tabak 2011:
        sec.insert("ihvat")                # From Halnes 2011:
        sec.insert("sk")                   # From Halnes 2011
        sec.insert("bk")                   # From Tabak 2011:

        sec.ek = -75                       # Reversal potential for potassium
        sec.eCa = 60                       # Reversal potential for calcium

        for seg in sec:
            seg.ftau_bk = tau_BK
            seg.alpha_Cadt = alpha
            seg.g_pas = g_l
            seg.e_pas = e_pas
            seg.gkdrbar_kdrt = g_K
            seg.ghvat_ihvat = g_Ca
            seg.gskbar_sk = g_SK
            seg.gbk_bk = g_BK

    return soma


def insert_current_clamp(input_site, duration=5000, delay=0, amplitude=0):
    """
    Inserts a current clamp in the neuron model.

    Parameters
    ----------
    input_site : neuron.Segment
        Where to place the current clamp. Example: soma(0.5), where 0.5 means 'center',
        0 would mean start, and 1 would mean at the end of the segment in question.
    duration : {float, int}, optional
        Duration of stimulus in ms. Default is 5000 ms.
    delay:
        Delay of stimulus in ms. Default is 0 ms.
    amplitude:
        Amplitude of stimulus in nA. Default is 0 nA.

    Returns
    -------
    stim : NEURON object current clamp
        The NEURON object current clamp. This must be returned, otherwise it is
        lost.
    """
    stim = nrn.IClamp(input_site)
    stim.delay = delay
    stim.dur = duration
    stim.amp = amplitude

    return stim


def run_simulation(soma, simulation_time=5000, noise_amplitude=0):
    """
    Runs the NEURON simulation.

    Parameters
    ----------
    record_site : neuron.Segment
        Where to record membrane potential from. Example: soma(0.5), where 0.5
        means 'center', 0 would mean start, and 1 would mean at the end of the
        segment in question.
    simulation_time : {float, int}, optional
        Simulation time in ms. Default is 5000 ms.
    noise_amplitude : float, optional
        The amplitude of the noise added to the model, in nA. If 0, no noise is added.
        Note that the model uses adaptive timesteps if there is no noise,
        and fixed timesteps with dt=0.01 if there is noise. Default is 0.

    Returns
    -------
    time : array
        Time array for the simulation.
    voltage : array
        Voltage array for the simulation.
    """
    rec_t, rec_v = record(soma(0.5))

    cvode = nrn.CVode()

    if noise_amplitude == 0:
        cvode.active(1)

        nrn.finitialize(-60)
        neuron.init()

        neuron.run(simulation_time)

    else:
        cvode.active(0)

        noise_stim = insert_current_clamp(soma(0.5), duration=simulation_time)

        nrn.dt = dt
        nrn.finitialize(-60)
        neuron.init()

        n_steps = int(np.ceil(simulation_time/nrn.dt)) + 1
        noise = noise_amplitude*np.random.normal(size=n_steps)/np.sqrt(nrn.dt)

        # Add noise
        i = 0
        while nrn.t < simulation_time:
            noise_stim.amp = noise[i]
            nrn.fadvance()

            i += 1

    return np.array(rec_t), np.array(rec_v)


def record(record_site):
    """
    Set up time and voltage recordings.

    Parameters
    ----------
    record_site : neuron.Segment
        Where to record voltage.

    Returns
    -------
    rec_t : neuron.hocObject : A Neuron Vector object.
        A Neuron Vector object for the time.
    rec_v : neuron.hocObject : A Neuron Vector object.
        A Neuron Vector object for the voltage.
    """
    rec_t = nrn.Vector()
    rec_t.record(nrn._ref_t)

    rec_v = nrn.Vector()
    rec_v.record(record_site._ref_v)

    return rec_t, rec_v


def tabak(g_l=g_l_scaled,
          e_pas=-50,
          g_K=g_K_scaled,
          g_Ca=g_Ca_scaled,
          g_SK=g_SK_scaled,
          g_BK=0,
          tau_BK=5,
          simulation_time=5000,
          noise_amplitude=0,
          discard=0,
          stimulus_amplitude=0):
    """
    Neuron reproduction of the model by Tabak et al. 2011.

    Parameters
    ----------
    g_l : float, optional
        The leak conductance, in S/cm^2. Default is 6.37e-5 S/cm^2.
    e_pas : float, optional
        Reversal potential for the leak current, in mV. Default is -50 mV.
    g_K : float, optional
        The maximal conductance of K channels, in S/cm^2. Default is
        9.55e-4 S/cm^2.
    g_Ca : float, optional
        The maximal conductance of Ca channels, in S/cm^2. Default is
        6.37e-4 S/cm^2.
    g_SK : float, optional
        The maximal conductance of SK channels, in S/cm^2. Default is
        6.37e-4 S/cm^2.
    g_BK : float, optional
        The maximal conductance of BK channels, in S/cm^2. Default is 0 S/cm^2.
    tau_BK : float, optional
        Time constant of the BK channel, in ms. Default is 5 ms.
    discard : {float, int}, optional
        The first ms of the simulation to be discarded. Default is 0 ms.
    simulation_time : {float, int}, optional
        Simulation time in ms. Default is 5000 ms.
    noise_amplitude : float, optional
        The amplitude of the noise added to the model, in nA. If 0, no noise is
        added. Note that the model uses adaptive timesteps if there is no noise,
        and fixed timesteps with dt=0.01 if there is noise. Default is 0.
        Original Tabak model has `noise_amplitude` = 0.004.
    stimulus_amplitude : float, optional
        The amplitude of the stimulus added to the model, in nA. Default is 0.

    Returns
    -------
    time : array
        Time array for the simulation.
    voltage : array
        Voltage array for the simulation.
    """
    soma = create_soma(g_l=g_l,
                       e_pas=e_pas,
                       g_K=g_K,
                       g_Ca=g_Ca,
                       g_SK=g_SK,
                       g_BK=g_BK,
                       tau_BK=tau_BK)


    stim = insert_current_clamp(soma(0.5),
                                duration=simulation_time,
                                amplitude=stimulus_amplitude)

    time, voltage = run_simulation(soma,
                                   simulation_time=simulation_time,
                                   noise_amplitude=noise_amplitude)

    return time[time > discard], voltage[time > discard]



if __name__ == '__main__':
    import matplotlib.pyplot as plt

    time, V = tabak(noise_amplitude=0.004, discard=1000)

    plt.style.use("seaborn-darkgrid")
    plt.plot(time, V)
    plt.savefig("voltage.png")
