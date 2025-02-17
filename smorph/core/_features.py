import numpy as npr
from skimage.morphology import skeletonize

from ..analysis.morphometric import (
    get_surface_area,
    pad_skeleton,
    get_soma_on_skeleton,
    get_total_length,
    get_avg_process_thickness,
    get_convex_hull,
    get_no_of_forks,
    classify_branching_structure,
    get_primary_branches,
    get_secondary_branches,
    get_tertiary_branches,
    get_quatenary_branches,
    get_terminal_branches,
    sholl_analysis
)
import numpy as np

def _extract_cell_features(cell, shell_step_size, polynomial_degree):
    """Returns all 23 Morphometric features from a cell image.

    Parameters
    ----------
    cell : Cell
        Cell object representing a cell of nervous system.
    shell_step_size : int
        Difference (in pixels) between concentric Sholl circles.
    polynomial_degree : int
        Degree of polynomial for fitting regression model on sholl values.

    Returns
    -------
    dict
        Represents all 23 morphological features interpreted from cell image.

    """
    cleaned_image = cell.cleaned_image

    surface_area = get_surface_area(cleaned_image)

    cell_skeleton = skeletonize(cleaned_image, method='lee')
    cell.skeleton = cell_skeleton

    # Skeletal features
    total_length = get_total_length(cell_skeleton)
    avg_process_thickness = get_avg_process_thickness(
        surface_area, total_length)
    convex_hull = get_convex_hull(cell)
    n_forks = get_no_of_forks(cell)
    try:

        soma_on_skeleton = get_soma_on_skeleton(
            cell.image, cell.image_type, cell_skeleton)

        (
            padded_skeleton,
            pad_sk_soma,
            bounded_skeleton_boundary,
            sk_soma
        ) = pad_skeleton(cell_skeleton, soma_on_skeleton)

        (
            branching_structure,
            terminal_branches,
            coords
        ) = classify_branching_structure(cell_skeleton, soma_on_skeleton)

        cell._padded_skeleton = padded_skeleton
        cell._pad_sk_soma = pad_sk_soma
        cell._branching_struct = branching_structure
        cell._branch_coords = coords

        (
            n_primary_branches,
            avg_length_of_primary_branches
        ) = get_primary_branches(branching_structure)
        (
            n_secondary_branches,
            avg_length_of_secondary_branches
        ) = get_secondary_branches(branching_structure)
        (
            n_tertiary_branches,
            avg_length_of_tertiary_branches
        ) = get_tertiary_branches(branching_structure)
        (
            n_quatenary_branches,
            avg_length_of_quatenary_branches
        ) = get_quatenary_branches(branching_structure)
        (
            n_terminal_branches,
            avg_length_of_terminal_branches
        ) = get_terminal_branches(terminal_branches)

        skeleton_ht = bounded_skeleton_boundary[3] - bounded_skeleton_boundary[2]
        skeleton_br = bounded_skeleton_boundary[1] - bounded_skeleton_boundary[0]

        largest_radius = np.max([sk_soma[1], abs(sk_soma[1]-skeleton_br),
                                sk_soma[0], abs(sk_soma[0]-skeleton_ht)])
        largest_radius = int(1.3 * largest_radius)
        sholl_results = sholl_analysis(shell_step_size, polynomial_degree,
                                        largest_radius, padded_skeleton,
                                        pad_sk_soma, n_primary_branches)

        cell._concentric_coords = sholl_results[8]
        cell._sholl_intersections = sholl_results[9]
        cell._sholl_polynomial_model = sholl_results[10]
        cell._non_zero_sholl_intersections = sholl_results[11]
        cell._polynomial_sholl_radii = sholl_results[12]
        features = {
        'surface_area': surface_area,
        'total_length': total_length,
        'avg_process_thickness': avg_process_thickness,
        'convex_hull': convex_hull,
        'no_of_forks': n_forks,
        'no_of_primary_branches': n_primary_branches,
        'no_of_secondary_branches': n_secondary_branches,
        'no_of_tertiary_branches': n_tertiary_branches,
        'no_of_quatenary_branches': n_quatenary_branches,
        'no_of_terminal_branches': n_terminal_branches,
        'avg_length_of_primary_branches': avg_length_of_primary_branches,
        'avg_length_of_secondary_branches': avg_length_of_secondary_branches,
        'avg_length_of_tertiary_branches': avg_length_of_tertiary_branches,
        'avg_length_of_quatenary_branches': avg_length_of_quatenary_branches,
        'avg_length_of_terminal_branches': avg_length_of_terminal_branches,
        'critical_radius': sholl_results[0],
        'critical_value': sholl_results[1],
        'enclosing_radius': sholl_results[2],
        'ramification_index': sholl_results[3],
        'skewness': sholl_results[4],
        'coefficient_of_determination': sholl_results[5],
        'sholl_regression_coefficient': sholl_results[6],
        'regression_intercept': sholl_results[7]
        }
    except:
            features = {
            'surface_area': surface_area,
            'total_length': total_length,
            'avg_process_thickness': avg_process_thickness,
            'convex_hull': convex_hull,
            'no_of_forks': n_forks,
            'no_of_primary_branches': 0,
            'no_of_secondary_branches': 0,
            'no_of_tertiary_branches': 0,
            'no_of_quatenary_branches': 0,
            'no_of_terminal_branches': 0,
            'avg_length_of_primary_branches': 0,
            'avg_length_of_secondary_branches': 0,
            'avg_length_of_tertiary_branches': 0,
            'avg_length_of_quatenary_branches': 0,
            'avg_length_of_terminal_branches': 0,
            'critical_radius': 0,
            'critical_value': 0,
            'enclosing_radius': 0,
            'ramification_index': 0,
            'skewness': 0,
            'coefficient_of_determination': 0,
            'sholl_regression_coefficient': 0,
            'regression_intercept': 0
        }


    return features
