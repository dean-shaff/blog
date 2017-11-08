"""
Generate some random data to plot in matplotlib. Outputs a csv file.
"""
import csv

import numpy as np
import matplotlib.pyplot as plt

def create_data(f_name=None, plot=False):
    """
    Create some noisy data with a linear trend and save to a file.
    Keyword Args:
        f_name (str): The name of the file to which to save data.
        plot (bool): Whether or not to plot the data.
    Returns:
        None
    """
    def linear_fn(m, b):
        """
        Create a linear function, with m as slope and b as y-intercept.
        Args:
            m (float): slope of function
            b (float): y-intercept
        Returns:
            callable
        """
        def fn(x):
            return m*x + b
        return fn

    linear = linear_fn(3., 0.)

    x = np.arange(4,12,1)
    y = linear(x) + 6*np.random.randn(5,x.shape[0])
    if f_name is not None:
        with open(f_name, "w") as f:
            writer = csv.writer(f,delimiter=",")
            writer.writerow(x)
            for i in range(y.shape[0]):
                writer.writerow(y[i,:])

    if plot:
        fig, ax = plt.subplots()
        ax.errorbar(x,np.mean(y,axis=0),yerr=np.std(y, axis=0),
                    fmt='o',capsize=3, elinewidth=1, color='green',
                    label="Some description of data")
        ax.set_xlabel("Simulated Independent Variable (units)")
        ax.set_ylabel("Simulated Dependent Variable, (units)")
        ax.set_title("Some Noisy Data with a linear trend")
        ax.legend()
        ax.grid(True)
        plt.show()

if __name__ == "__main__":
    create_data("./sample_data.csv")
