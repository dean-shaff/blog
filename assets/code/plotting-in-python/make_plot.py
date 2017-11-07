"""
Given some csv file, create a plot, with errorbars in the Y direction.
"""
import csv

import numpy as np
import matplotlib.pyplot as plt

def load_data_from_csv(f_name):
    """
    Auxillary function to get data from csv file.
    Args:
        f_name (str): The path to the data file.
    Returns:
        tuple: (x, y), both np.ndarray.
    """
    data = []
    f = open(f_name, "r")
    reader = csv.reader(f,delimiter=",")
    for row in reader:
        data.append([float(i) for i in row])
    f.close()
    data = np.array(data)
    x = np.arange(data.shape[0])
    return x, data

def plot_data(f_name):
    """
    Plot data and associated error bars from a given csv file.
    Args:
        f_name (str): The name of the file that contains data to plot.
    Returns:
        None
    """
    # The load_data_from_csv function is a utility function that will dump our
    # csv data into an array called data.
    x, data = load_data_from_csv(f_name)
    # plt.subplots is a way of initializing matplotlib so you can plot
    fig, ax = plt.subplots()
    # ax.errorbar is the main plotting function call.
    # The `fmt`, `capsize`, `elinewidth`, `color` and `label` keyword
    # arguments are there to style the plot -- they are not instrumental.
    ax.errorbar(x,np.mean(data, axis=1),yerr=np.std(data,axis=1),
                fmt='o',capsize=3, elinewidth=1, color='green',
                label="Some description of data")
    # Set the text on the x axis.
    ax.set_xlabel("Simulated Independent Variable (units)")
    # Set the text on the y axis.
    ax.set_ylabel("Simulated Dependent Variable, (units)")
    # Set the text for the title.
    ax.set_title("Some Noisy Data with a linear trend")
    # Turn on the legend box that appears on the plot figure.
    ax.legend()
    # Turn on grid lines
    ax.grid(True)
    # Create a window with the plot. You can click the save icon to
    # save it to file. Alternatively, you can uncomment the
    # `fig.savefig("sample_data_plot.png")` line to save directly.
    plt.show()
    # fig.savefig("sample_data_plot.png")

if __name__ == "__main__":
    plot_data("./sample_data.csv")
