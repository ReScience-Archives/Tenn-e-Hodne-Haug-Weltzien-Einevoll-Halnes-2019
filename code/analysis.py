# To work with Python 2.7
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import multiprocessing as mp
import numpy as np

import matplotlib.pyplot as plt

from tqdm import tqdm

from tabak import scale_conductance, tabak, scale_capacitance, scale_alpha, scale_tabak
from tabak import G_l, G_K, G_SK, G_Ca, C, Alpha
from burstiness import burstiness, duration, burst_threshold


# Simulation and analysis parameters
discard = 10000                # ms
simulation_time = 60000        # ms
noise_amplitude = 0.004        # nA
simulation_time_plot = 15000   # ms

robustness_reruns = 512        # From original article

A = 3.1415927e-6
dt = 0.01

# Equivalent to ../article/figures
figure_folder = os.path.join(os.pardir, "article", "figures")
data_folder = "data"
output_file = "robustness.txt"

# Plotting parameters
figure_width = 7.08
titlesize = 13
labelsize = 11
fontsize = 8
fontweight = "medium"
plot_label_weight = "bold"
figure_format = ".eps"
label_x = -0.08
label_y = 1.08
axis_grey = (0.6, 0.6, 0.6)


# Set the random seed to increase reproducability
np.random.seed(10)


# Set default options for plotting
params = {
    "xtick.color": axis_grey,
    "ytick.color": axis_grey,
    "axes.edgecolor": axis_grey,
    "xtick.bottom": True,
    "ytick.left": True,
    "axes.spines.bottom": True,
    "axes.spines.left": True,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 1,
    "axes.labelsize": labelsize,
    "font.family": "serif",
}


def calculate_frequency_bf(**parameters):
    """
    Calculate the frequency of a binned burstiness factor from a series of
    model evaluations.

    Parameters
    ----------
    **parameters
        Any number of optional parameters passed on to the model.

    Returns
    -------
    bins : numpy.array
        The bins for the event durations.
    frequency : numpy.array
        Frequency of occurrences in each binned event duration
    burstiness_factor : float
        The fraction of events that is above `burst_threshold`, for all
        reruns.

    Notes
    -----
    """
    nr_bins = 40
    hist_range = (0, 200)
    time, voltage = tabak(noise_amplitude=noise_amplitude,
                          discard=discard,
                          simulation_time=simulation_time,
                          **parameters)

    event_durations = duration(time, voltage)

    binned_durations, bins = np.histogram(event_durations, bins=nr_bins, range=hist_range)
    frequency = binned_durations/binned_durations.sum()

    burstiness_factor = burstiness(event_durations)

    return bins, frequency, burstiness_factor


def change_g_BK():
    """
    Change g_BK values and calculate the burstiness factor for each.

    Returns
    -------
    G_BKs : numpy.array
        The g_BK values in nS.
    burstiness_factors : list
        The burstiness factor for each G_BK, where the burstiness factor is
        the fraction of events that is above `burst_threshold`.
    """
    G_BKs = np.array([0, 0.2, 0.4, 0.5, 0.6, 0.8, 1])

    g_BKs = scale_conductance(G_BKs, A)

    parameters = scale_tabak(A)
    del parameters["g_BK"]

    burstiness_factors = []

    for g_BK in g_BKs:
        bins, frequency, burstiness_factor = calculate_frequency_bf(g_BK=g_BK,
                                                                    A=A,
                                                                    dt=dt,
                                                                    **parameters)
        burstiness_factors.append(burstiness_factor)

    return G_BKs, burstiness_factors


def change_tau_BK():
    """
    Change tau_BK values and calculate the burstiness factor for each.

    Returns
    -------
    tau_BKs : numpy.array
        The tau_BK values in ms.
    burstiness_factors : list
        The burstiness factor for each tau_BK, where the burstiness factor is
        the fraction of events that is above `burst_threshold`.

    Notes
    -----
    Uses original G_BK = 1.
    """
    tau_BKs = np.array([2, 4, 5, 6, 7, 8, 10])

    burstiness_factors = []

    # Original values (scaled to the new model)
    parameters = scale_tabak(A)
    parameters["g_BK"] = scale_conductance(1, A)

    for tau_BK in tau_BKs:
        bins, frequency, burstiness_factor = calculate_frequency_bf(tau_BK=tau_BK,
                                                                    A=A,
                                                                    dt=dt,
                                                                    **parameters)
        burstiness_factors.append(burstiness_factor)

    return tau_BKs, burstiness_factors


def tabak_parallel(parameters):
    """
    Wrapper for the Tabak model, for use in parallel runs.

    Parameters
    ----------
    parameters: array_like
        The parameters grouped so each element is a list of all parameters
        for the model, on the form [g_BK, g_K, g_Ca, g_SK, g_l, A, dt].

    Returns
    -------
    burstiness_factor : float
        The fraction of events that is above `burst_threshold`.
    """
    A = parameters[5]

    c_scaled = scale_capacitance(C, A)
    alpha_scaled = scale_alpha(Alpha, A)

    time, voltage = tabak(noise_amplitude=noise_amplitude,
                          discard=discard,
                          simulation_time=simulation_time,
                          g_BK=parameters[0],
                          g_K=parameters[1],
                          g_Ca=parameters[2],
                          g_SK=parameters[3],
                          g_l=parameters[4],
                          c=c_scaled,
                          alpha=alpha_scaled,
                          A=A,
                          dt=parameters[6])

    # TODO remove this
    # if voltage.max() - voltage.min() < 30:
    #     return None

    event_durations = duration(time, voltage)

    burstiness_factor = burstiness(event_durations)

    return burstiness_factor


def robustness(g_BK=0, A=3.1415927e-6, dt=0.01):
    """
    Calculate the number of occurrences for binned burstiness factor of several
    model runs with varying conductances (except g_BK).

    Parameters
    ----------
    g_BKs : float
        The value of the g_BK conductance in S/cm^2.
    A : float, optional
        Area of the neuron cell, in cm^2. Default is 3.1415927e-6.
    dt : float, optional
        Time step of the simulation. Only used when there is noise,
        otherwise adaptive time steps is used. Default is 0.01.

    Returns
    -------
    bins : numpy.array
        The bins for the burstiness.
    binned_burstiness_factors : numpy.array
        The number of model evaluations with burstiness factor corresponding to
        each bin.
    spikers : float
        Fraction of model evaluations with results that have
        burstiness factor < 0.3.
    bursters : float
        Fraction of model evaluations with results that have
        burstiness factor > 0.5.
    """
    bins = 10
    hist_range = (0, 1)

    # Original values (scaled to the new model)
    g_l_scaled = scale_conductance(G_l, A)
    g_K_scaled = scale_conductance(G_K, A)
    g_Ca_scaled = scale_conductance(G_Ca, A)
    g_SK_scaled = scale_conductance(G_SK, A)

    # Draw conductances from uniform distributions +/- 50% of their original values
    g_K = np.random.uniform(g_K_scaled*0.5, g_K_scaled*1.5, robustness_reruns)
    g_Ca = np.random.uniform(g_Ca_scaled*0.5, g_Ca_scaled*1.5, robustness_reruns)
    g_SK = np.random.uniform(g_SK_scaled*0.5, g_SK_scaled*1.5, robustness_reruns)
    g_l = np.random.uniform(g_l_scaled*0.5, g_l_scaled*1.5, robustness_reruns)

    g_BKs = np.ones(robustness_reruns)*g_BK
    As = np.ones(robustness_reruns)*A
    dts = np.ones(robustness_reruns)*dt
    parameters = np.array([g_BKs, g_K, g_Ca, g_SK, g_l, As, dts]).T

    # Run the model for each of the selected conductances
    # and calculate the burstiness factor of each evaluation
    pool = mp.Pool(processes=mp.cpu_count() - 2)

    burstiness_factors = []
    for burstiness_factor in tqdm(pool.imap(tabak_parallel, parameters),
                                  desc="Running model",
                                  total=robustness_reruns):

        if burstiness_factor is not None:
            burstiness_factors.append(burstiness_factor)

    pool.close()

    burstiness_factors = np.array(burstiness_factors)

    binned_burstiness_factors, bins = np.histogram(burstiness_factors, bins=bins, range=hist_range)

    bursters = len(np.where(burstiness_factors > 0.5)[0])/len(burstiness_factors)
    spikers = len(np.where(burstiness_factors < 0.3)[0])/len(burstiness_factors)

    return bins, binned_burstiness_factors, bursters, spikers




def figure_1():
    """
    Reproduce figure 1 in Tabak et. al. 2011. Figure is saved as figure_1

    http://www.jneurosci.org/content/31/46/16855/tab-article-info
    """
    print("Reproducing figure 1 in Tabak et. al. 2011")

    parameters = scale_tabak(A)

    # G_BK = 0
    parameters["g_BK"] = scale_conductance(0, A)

    time_0, V_0 = tabak(noise_amplitude=noise_amplitude,
                        discard=discard,
                        simulation_time=simulation_time,
                        A=A,
                        dt=dt,
                        **parameters)

    bins_0, frequency_0, burstiness_factor_0 = calculate_frequency_bf(A=A,
                                                                      dt=dt,
                                                                      **parameters)

    # G_BK = 0.5
    parameters["g_BK"] = scale_conductance(0.5, A)

    time_05, V_05 = tabak(noise_amplitude=noise_amplitude,
                          discard=discard,
                          simulation_time=simulation_time,
                          A=A,
                          dt=dt,
                          **parameters)

    bins_05, frequency_05, burstiness_factor_05 = calculate_frequency_bf(A=A,
                                                                         dt=dt,
                                                                         **parameters)


    # G_BK = 1
    parameters["g_BK"] = scale_conductance(1, A)
    time_1, V_1 = tabak(noise_amplitude=noise_amplitude,
                        discard=discard,
                        simulation_time=simulation_time,
                        A=A,
                        dt=dt,
                        **parameters)

    bins_1, frequency_1, burstiness_factor_1 = calculate_frequency_bf(A=A,
                                                                      dt=dt,
                                                                      **parameters)


    # Calculate results for figure 1D
    scaled_g_BKs, burstiness_factors_g_BK = change_g_BK()

    # Calculate results for figure 1E
    scaled_tau_BK, burstiness_factors_tau_BK = change_tau_BK()

    # "Remove" the discarded time to plot from 0
    time_0 -= discard
    time_05 -= discard
    time_1 -= discard

    # Rescale from ms to s
    time_0 /= 1000
    time_05 /= 1000
    time_1 /= 1000
    bins_0 /= 1000
    bins_05 /= 1000
    bins_1 /= 1000
    burst_threshold_scaled = burst_threshold/1000
    simulation_time_plot_scaled = simulation_time_plot/1000
    discard_scaled = discard/1000


    # Plot the data
    plt.rcParams.update(params)

    plt.figure(figsize=(figure_width, figure_width))
    gs = plt.GridSpec(4, 6)
    ax1 = plt.subplot(gs[0, :-2])
    ax2 = plt.subplot(gs[1, :-2])
    ax3 = plt.subplot(gs[2, :-2])

    ax4 = plt.subplot(gs[0, -2:])
    ax5 = plt.subplot(gs[1, -2:])
    ax6 = plt.subplot(gs[2, -2:])

    ax7 = plt.subplot(gs[3, :3])
    ax8 = plt.subplot(gs[3, 3:])


    voltage_axes = [ax1, ax2, ax3]
    burst_axes = [ax4, ax5, ax6]

    ax1.plot(time_0, V_0)
    title = r"$G_{\mathrm{BK}} = 0 $ nS"
    ax1.set_title(title,  fontweight=fontweight)
    ax1.text(label_x,
             label_y,
             "A",
             transform=ax1.transAxes,
             fontsize=titlesize,
             fontweight=plot_label_weight)

    ax2.plot(time_05, V_05)
    title = r"$G_{\mathrm{BK}} = 0.5 $ nS"
    ax2.set_title(title, fontweight=fontweight)
    ax2.text(label_x,
             label_y,
             "B",
             transform=ax2.transAxes,
             fontsize=titlesize,
             fontweight=plot_label_weight)

    ax3.plot(time_1, V_1)
    title = r"$G_{\mathrm{BK}} = 1$ nS"
    ax3.set_title(title, fontweight=fontweight)
    ax3.set_xlabel("Time (s)", fontsize=labelsize, fontweight=fontweight)
    ax3.text(label_x, label_y, "C", transform=ax3.transAxes, fontsize=titlesize, fontweight=plot_label_weight)


    yticks = [-60, -40, -20, 0]
    xticks = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5]

    for ax in voltage_axes:
        ax.set_ylabel("V (mV)", fontweight=fontweight)
        ax.set_ylim([-70, 10])
        ax.set_xlim([0, simulation_time_plot_scaled - discard_scaled])
        ax.set_yticks(yticks)
        ax.set_xticks(xticks)
        ax.tick_params(axis="both", which="major", labelsize=fontsize, labelcolor="black")


    ax4.bar(bins_0[:-1], frequency_0, width=(bins_0[1] - bins_0[0]), align="edge")
    ax4.text(0.1, 0.8, "BF = {}".format(burstiness_factor_0), fontsize=labelsize)

    ax5.bar(bins_05[:-1], frequency_05, width=(bins_05[1] - bins_05[0]), align="edge")
    ax5.text(0.1, 0.8, "BF = {:.2f}".format(burstiness_factor_05), fontsize=labelsize)
    ax5.text(0.002, 0.4, "Spikes", fontsize=8)
    ax5.text(0.1, 0.4, "Bursts", fontsize=8)

    ax6.bar(bins_1[:-1], frequency_1, width=(bins_1[1] - bins_1[0]), align="edge")
    ax6.text(0.1, 0.8, "BF = {:.2f}".format(burstiness_factor_1), fontsize=labelsize)

    yticks = [0, 0.2, 0.4, 0.6, 0.8, 1]
    xticks = [0, 0.05, 0.1, 0.15, 0.2]


    for ax in burst_axes:
        ax.axvline(burst_threshold_scaled, color=axis_grey)
        ax.set_ylim([0, 1])
        ax.set_xlim([0, .23])
        ax.set_yticks(yticks)
        ax.set_xticks(xticks)
        ax.set_ylabel("Frequency", fontweight=fontweight)
        ax.tick_params(axis="both", which="major", labelsize=fontsize, labelcolor="black")

    ax6.set_xlabel("Event duration (s)", fontweight=fontweight)


    ax7.plot(scaled_g_BKs, burstiness_factors_g_BK, marker=".")
    ax7.set_xlabel(r"$G_{\mathrm{BK}}$ (nS)", fontweight=fontweight)
    ax7.set_ylabel("Burstiness", fontweight=fontweight)
    ax7.tick_params(axis="both", which="major", labelsize=fontsize, labelcolor="black")
    ax7.set_yticks(yticks)
    ax7.set_ylim([-0.05, 1.05])


    ax8.plot(scaled_tau_BK, burstiness_factors_tau_BK, marker=".")
    ax8.set_xlabel(r"$\tau_{\mathrm{BK}}$ (ms)", fontweight=fontweight)
    ax8.set_ylabel("Burstiness", fontweight=fontweight)
    ax8.set_yticks(yticks)
    ax8.tick_params(axis="both", which="major", labelsize=fontsize, labelcolor="black")
    ax8.set_ylim([-0.05, 1.05])
    ax8.set_xlim([2, 10])

    ax7.text(label_x,
             label_y,
             "D",
             transform=ax7.transAxes,
             fontsize=titlesize,
             fontweight=plot_label_weight)
    ax8.text(label_x,
             label_y,
             "E",
             transform=ax8.transAxes,
             fontsize=titlesize,
             fontweight=plot_label_weight)

    plt.tight_layout()

    plt.savefig(os.path.join(figure_folder, "figure_1" + figure_format))


def generate_data_figure_2():
    """
    Reproduce the data for figure 2 in Tabak et. al. 2011.

    Returns
    -------
    bins_0 : array
        Bins for the binned burstiness factors when G_BK = 0.
    bins_05 : array
        Bins for the binned burstiness factors when G_BK = 05.
    bins_1 : array
        Bins for the binned burstiness factors when G_BK = 1.
    binned_burstiness_factors_0 : array
        Binned burstiness factors when G_BK = 0.
    binned_burstiness_factors_05 : array
        Binned burstiness factors when G_BK = 0.5.
    binned_burstiness_factors_1 : array
        Binned burstiness factors when G_BK = 1.

    Notes
    -----
    http://www.jneurosci.org/content/31/46/16855/tab-article-info
    """
    # Run model for various G_BK values
    # G_BK = 0
    print("Running for G_BK = 0")

    g_BK = scale_conductance(0, A)
    bins_0, binned_burstiness_factors_0, bursters_0, spikers_0 = robustness(g_BK=g_BK, dt=dt)

    # G_BK = 0.5
    print("Running for G_BK = 0.5")

    g_BK = scale_conductance(0.5, A)
    bins_05, binned_burstiness_factors_05, bursters_05, spikers_05 = robustness(g_BK=g_BK, dt=dt)

    # G_BK = 1
    print("Running for G_BK = 1")

    g_BK = scale_conductance(1, A)
    bins_1, binned_burstiness_factors_1, bursters_1, spikers_1 = robustness(g_BK=g_BK, dt=dt)


    # Write percentage of events as spikers and bursters to file
    with open(os.path.join(data_folder, output_file), "w") as output:
        output.write("G_BK = 0\n")
        output.write("Spikers = {}\n".format(spikers_0))
        output.write("Bursters = {}\n\n".format(bursters_0))

        output.write("G_BK = 0.5\n")
        output.write("Spikers = {}\n".format(spikers_05))
        output.write("Bursters = {}\n\n".format(bursters_05))

        output.write("G_BK = 1\n")
        output.write("Spikers = {}\n".format(spikers_1))
        output.write("Bursters = {}\n".format(bursters_1))


    np.save(os.path.join(data_folder, "bins_0"), bins_0)
    np.save(os.path.join(data_folder, "bins_05"), bins_05)
    np.save(os.path.join(data_folder, "bins_1"), bins_1)
    np.save(os.path.join(data_folder, "binned_burstiness_factors_0"), binned_burstiness_factors_0)
    np.save(os.path.join(data_folder, "binned_burstiness_factors_05"), binned_burstiness_factors_05)
    np.save(os.path.join(data_folder, "binned_burstiness_factors_1"), binned_burstiness_factors_1)

    return bins_0, bins_05, bins_1, binned_burstiness_factors_0, binned_burstiness_factors_05, binned_burstiness_factors_1


def load_results_figure_2():
    """
    Load results saved when generating results for figure 2.

    Returns
    -------
    bins_0 : array
        Bins for the binned burstiness factors when G_BK = 0.
    bins_05 : array
        Bins for the binned burstiness factors when G_BK = 05.
    bins_1 : array
        Bins for the binned burstiness factors when G_BK = 1.
    binned_burstiness_factors_0 : array
        Binned burstiness factors when G_BK = 0.
    binned_burstiness_factors_05 : array
        Binned burstiness factors when G_BK = 0.5.
    binned_burstiness_factors_1 : array
        Binned burstiness factors when G_BK = 1.

    """
    bins_0 = np.load(os.path.join(data_folder, "bins_0.npy"))
    bins_05 = np.load(os.path.join(data_folder, "bins_05.npy"))
    bins_1 = np.load(os.path.join(data_folder, "bins_1.npy"))
    binned_burstiness_factors_0 = np.load(os.path.join(data_folder, "binned_burstiness_factors_0.npy"))
    binned_burstiness_factors_05 = np.load(os.path.join(data_folder, "binned_burstiness_factors_05.npy"))
    binned_burstiness_factors_1 = np.load(os.path.join(data_folder, "binned_burstiness_factors_1.npy"))

    return bins_0, bins_05, bins_1, binned_burstiness_factors_0, binned_burstiness_factors_05, binned_burstiness_factors_1


def plot_figure_2(bins_0,
                  bins_05,
                  bins_1,
                  binned_burstiness_factors_0,
                  binned_burstiness_factors_05,
                  binned_burstiness_factors_1):
    """
    Create figure 2 in Tabak et. al. 2011 from data. Figure is saved as
    ../article/figure_2.eps.

    Parameters
    ----------
    bins_0 : array
        Bins for the binned burstiness factors when G_BK = 0.
    bins_05 : array
        Bins for the binned burstiness factors when G_BK = 05.
    bins_1 : array
        Bins for the binned burstiness factors when G_BK = 1.
    binned_burstiness_factors_0 : array
        Binned burstiness factors when G_BK = 0.
    binned_burstiness_factors_05 : array
        Binned burstiness factors when G_BK = 0.5.
    binned_burstiness_factors_1 : array
        Binned burstiness factors when G_BK = 1.
    """
    plt.rcParams.update(params)

    fig, axes = plt.subplots(nrows=3, figsize=(figure_width, 1.5*figure_width))

    ax1 = axes[0]
    ax2 = axes[1]
    ax3 = axes[2]

    increased_titlesize = titlesize + 2
    ax1.text(label_x, label_y, "A", transform=ax1.transAxes, fontsize=increased_titlesize, fontweight="bold")
    ax2.text(label_x, label_y, "B", transform=ax2.transAxes, fontsize=increased_titlesize, fontweight="bold")
    ax3.text(label_x, label_y, "C", transform=ax3.transAxes, fontsize=increased_titlesize, fontweight="bold")

    ax1.bar(bins_0[:-1], binned_burstiness_factors_0, width=(bins_0[1] - bins_0[0]), align="edge")
    title = r"$G_{\mathrm{BK}} = 0$ nS"
    ax1.set_title(title, fontsize=increased_titlesize, fontweight=fontweight)

    ax2.bar(bins_05[:-1], binned_burstiness_factors_05, width=(bins_05[1] - bins_05[0]), align="edge")
    title = r"$G_{\mathrm{BK}} = 0.5$ nS"
    ax2.set_title(title, fontsize=increased_titlesize, fontweight=fontweight)

    ax3.bar(bins_1[:-1], binned_burstiness_factors_1, width=(bins_1[1] - bins_1[0]), align="edge")
    title = r"$G_{\mathrm{BK}} =  1$ nS"
    ax3.set_title(title, fontsize=increased_titlesize, fontweight=fontweight)

    xticks = np.arange(0, 1.1, 0.2)

    for ax in [ax1, ax2, ax3]:
        ax.set_ylim([0, 450])
        ax.set_xticks(xticks)
        ax.set_ylabel("Number of models", fontweight=fontweight, fontsize=titlesize)
        ax.set_xlabel("Burstiness", fontweight=fontweight, fontsize=titlesize)
        ax.tick_params(axis="both", which="major", labelsize=labelsize, labelcolor="black")


    plt.tight_layout()

    plt.savefig(os.path.join(figure_folder, "figure_2" + figure_format))


def figure_2():
    """
    Reproduce figure 2 in Tabak et. al. 2011. Figure is saved as
    ../article/figure_2.eps.

    http://www.jneurosci.org/content/31/46/16855/tab-article-info
    """

    print("Reproducing figure 2 in Tabak et. al. 2011")
    results = generate_data_figure_2()
    # This can be used to load previously generated results
    # results = load_results_figure_2()

    plot_figure_2(*results)


if __name__ == "__main__":
    figure_1()
    figure_2()