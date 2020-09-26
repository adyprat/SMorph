import matplotlib.pyplot as plt
import numpy as np
from copy import deepcopy
from matplotlib.colors import is_color_like
from skimage.color import rgb2gray

from ._features import extract_features
from ..util import preprocess_image


class Cell:
    """
    Container object for single cell analysis.

    Attributes
    ----------
    image : ndarray
        RGB or Grayscale image data of cell of nervous system.
    image_type : str
        Neuroimaging technique used to get image data of neuronal cell,
        either 'confocal' or 'DAB'.
    cleaned_image : ndarray
        Thresholded, denoised, boolean transformation of `image` with solid
        soma.
    features : dict
        23 Morphometric features derived of the cell.
    skeleton : ndarray
        2D skeletonized, boolean transformation of `image`.
    convex_hull : ndarray
        2D transformation of `skeleton` representing a convex envelope
        that contains it.

    """
    __slots__ = ('image', 'image_type', 'cleaned_image', 'features',
                 'convex_hull', 'skeleton', '_fork_coords', '_branch_coords',
                 '_branching_structure', '_concentric_coords', '_sholl_radii',
                 '_sholl_intersections', '_padded_skeleton', '_pad_sk_soma',
                 '_sholl_polynomial_model', '_polynomial_sholl_radii',
                 '_non_zero_sholl_radii', '_non_zero_sholl_intersections')

    def __init__(self, cell_image, image_type, reference_image=None, shell_step_size=3, polynomial_degree=3):
        self.image = (cell_image if cell_image.ndim == 2
                      else rgb2gray(cell_image))
        self.image_type = image_type
        self.cleaned_image = preprocess_image(
            self.image, image_type, reference_image)
        self.features = extract_features(
            self, shell_step_size, polynomial_degree)

    def plot_convex_hull(self):
        """Plots convex hull of the skeleton of the cell."""
        ax = plt.subplots()[1]
        ax.set_axis_off()
        ax.imshow(self.convex_hull)

    def plot_forks(self, highlightcolor='g'):
        """Plots skeleton of the cell with all furcations highlighted.

        Parameters
        ----------
        highlightcolor : str, optional
            Color for highlighting the forks, by default 'g'

        """
        if not is_color_like(highlightcolor):
            print(f'{highlightcolor} is not a valid color. '
                  'Resetting highlight color to green.')
            highlightcolor = 'g'

        fork_coords = self._fork_coords
        ax = plt.subplots(figsize=(4, 4))[1]
        ax.set_title('path')
        ax.imshow(self.skeleton, interpolation='nearest')

        for i in fork_coords:
            c = plt.Circle((i[1], i[0]), 0.6, color=highlightcolor)
            ax.add_patch(c)

        ax.set_axis_off()
        plt.tight_layout()
        plt.show()

    def plot_branching_structure(self, colors=['r','b','m','g','c']):
        """Plots skeleton of the cell with all levels of branching highlighted.

        Parameters
        ----------
        colors : list, optional
            List of colors that distinctively highlight all levels of branching
            -- primary, secondary, tertiary, quaternary, & terminal,
            respectively, by default ['r','b','m','g','c']

        """
        color_validations = list(map(is_color_like, colors))
        if sum(color_validations) != len(color_validations):
            print(f'{colors} is not a valid list of colors. '
                  'Resetting colors to ["r","b","m","g","c"].')
            colors = ['r','b','m','g','c']

        branching_structure = self._branching_structure
        coords = self._branch_coords
        # store same level branch nodes in single array
        color_branches_coords = []
        for branch_level in branching_structure:
            single_branch_level = []
            for path in branch_level:
                path_coords = []
                for node in path:
                    path_coords.append(coords[node])
                    single_branch_level.extend(path_coords)
            color_branches_coords.append(single_branch_level)

        ax = plt.subplots(figsize=(4, 4))[1]
        ax.set_title('path')
        ax.imshow(self.skeleton, interpolation='nearest')

        for j, color_branch in enumerate(color_branches_coords):
            if j > 4:
                j = 4
            for k in color_branch:
                c = plt.Circle((k[1], k[0]), 0.5, color=colors[j])
                ax.add_patch(c)

        ax.set_axis_off()
        plt.tight_layout()
        plt.show()

    def plot_sholl_results(self, somacolor='r'):
        """Plots results of Sholl Analysis.

        This individually plots cell skeleton with sholl circles & Sholl radii
        vs intersections plot.

        Parameters
        ----------
        somacolor : str, optional
            Color to highligh the skeleton soma, by default 'r'

        """
        if not is_color_like(somacolor):
            print(f'{somacolor} is not a valid color. '
                  'Resetting highlight color to red.')
            somacolor = 'r'

        concentric_coordinates = self._concentric_coords
        cell_padded_skeleton = deepcopy(self._padded_skeleton)
        for coordinates in concentric_coordinates.values():
            for coord in coordinates:
                cell_image_with_circles = cell_padded_skeleton
                cell_image_with_circles[coord[0], coord[1]] = 1

        # plot circles on skeleton
        ax = plt.subplots(figsize=(10, 6))[1]
        ax.imshow(cell_image_with_circles)
        # overlay soma on skeleton
        y, x = self._pad_sk_soma
        c = plt.Circle((x, y), 1, color=somacolor, alpha=.9)
        ax.add_patch(c)
        ax.set_axis_off()
        plt.tight_layout()
        plt.show()

        # plot sholl graph showing radius vs. n_intersections
        plt.plot(self._sholl_radii, self._sholl_intersections)
        plt.xlabel("Distance from centre")
        plt.ylabel("No. of intersections")
        plt.show()

    def plot_polynomial_fit(self):
        """Plots original & estimated no. of intersections vs. Sholl radii.
        
        Plots polynomial regression curve describing the relationship between
        no. of intersections vs. Sholl radii, & observed values from the cell
        skeleton.

        """
        last_intersection_idx = np.max(np.nonzero(self._sholl_intersections))
        non_zero_radii = self._sholl_radii[:last_intersection_idx]
        x_ = self._polynomial_sholl_radii
        y_data = self._non_zero_sholl_intersections
        # predict y from the data
        reshaped_x = non_zero_radii.reshape((-1, 1))

        y_new = self._sholl_polynomial_model.predict(x_)
        # plot the results
        plt.figure(figsize=(4, 3))
        ax = plt.axes()
        ax.scatter(reshaped_x, y_data)
        ax.plot(non_zero_radii, y_new)
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.axis('tight')
        plt.show()
