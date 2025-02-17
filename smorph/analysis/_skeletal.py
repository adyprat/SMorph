import numpy as np
from scipy.ndimage import generate_binary_structure, label
from skan.csr import skeleton_to_csgraph,make_degree_image
from skan.csr import Skeleton, summarize
from skimage.feature import blob_log
from skimage.morphology import convex_hull_image
from skimage.util import invert
from skimage.morphology import skeletonize
import cv2

def _get_blobs(cell_image, image_type):
    """Extracts circular blobs in cell image for finding soma later.

    Parameters
    ----------
    cell_image : ndarray
        Grayscale image data of cell of nervous system.
    image_type : str
        Neuroimaging technique used to get image data of neuronal cell,
        either 'confocal' or 'DAB'.

    Returns
    -------
    ndarray
        Coordinates & radius of each blob.
    """

    if image_type == "DAB":
        min_sigma, max_sigma, num_sigma = 6, 20, 10
        #threshold, overlap = 0.1, 0.5
        threshold, overlap = 0.0, 0.5
        image = cell_image# invert(cell_image)
    elif image_type == "confocal":
        min_sigma, max_sigma, num_sigma = 3, 20, 10
        threshold, overlap = 0.1, 0.5
        image = cell_image

    blobs_log = blob_log(image, min_sigma=min_sigma,
                         max_sigma=max_sigma, num_sigma=num_sigma,
                         threshold=threshold, overlap=overlap)

    def eliminate_border_blobs(blobs_log):
        """Find the blobs too close to border so as to eliminate them."""
        border_x = image.shape[1] / 5
        border_y = image.shape[0] / 5

        filtered_blobs = blobs_log[(border_x < blobs_log[:, 1]) &
                                   (blobs_log[:, 1] < 4*border_x) &
                                   (border_y < blobs_log[:, 0]) &
                                   (blobs_log[:, 0] < 4*border_y)]

        return filtered_blobs

    blobs_log = eliminate_border_blobs(blobs_log)

    if len(blobs_log) < 1:
        # if none of the blobs remain after border blob elimination,
        # try blob_log with less stringent parameters
        while len(blobs_log) < 1 and min_sigma > 2:  # TODO: handle fail
            min_sigma -= 1
            blobs_log = blob_log(image, min_sigma, max_sigma,
                                 num_sigma, threshold, overlap)
            blobs_log = eliminate_border_blobs(blobs_log)

    if len(blobs_log) < 1:
        raise RuntimeError('No blob detected for the soma!')

    return blobs_log


def _centre_of_mass(blobs, cell_image, image_type):
    """Finds centre of mass of the multiple blobs detected.

    Find the blob with highest intensity value.
    """
    ixs = np.indices(cell_image.shape)

    n_blobs = blobs.shape[0]
    blob_centres = blobs[:, 0:2]
    blob_radii = blobs[:, 2]

    centres = blob_centres[..., np.newaxis, np.newaxis]
    radii = np.square(blob_radii)[:, np.newaxis, np.newaxis]
    # Using the formula for a circle, `x**2 + y**2 < r**2`,
    # generate a mask for all blobs.
    mask = np.square(ixs - centres).sum(axis=1) < radii
    # Calculate the average intensity of pixels under the mask
    blob_intensities = np.full(
        (n_blobs, *ixs.shape[1:]), cell_image)
    blob_intensities = (blob_intensities * mask).reshape(mask.shape[0], -1)
    blob_intensities[blob_intensities < .02 * blob_intensities.max()] = 0
    blob_intensities = blob_intensities.sum(1) * (blob_intensities != 0).sum(1)

    if image_type == "DAB":
        max_intensity = blob_centres[np.argmin(blob_intensities)]

        return max_intensity

    elif image_type == "confocal":
        max_radius_idx = np.argmax(blob_radii)
        max_intensity_idx = np.argmax(blob_intensities)
        max_radius = blob_centres[max_radius_idx]
        max_intensity = blob_centres[max_intensity_idx]
        if np.count_nonzero(blob_radii == blob_radii[max_radius_idx]) > 1:
            return max_intensity
        return max_radius


def _get_soma(cell_image, image_type):
    """Calculate pixel position to be attribute as soma."""

    # soma_blobs = _get_blobs(cell_image, image_type)

    # if len(soma_blobs) == 0:
    #     raise RuntimeError('No soma detected for the cell!')
    # if len(soma_blobs) == 1:
    #     soma = soma_blobs[0][:2]
    # if len(soma_blobs) > 1:
    #     #soma = _centre_of_mass(soma_blobs, cell_image, image_type)
    #     soma = soma_blobs[np.argmax(soma_blobs[:, 2]),:2]
    
    dist_map = cv2.distanceTransform(cell_image.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    _,radius, _, center = cv2.minMaxLoc(dist_map)
    return (center[1], center[0])


def get_surface_area(cleaned_image_filled_holes):
    return np.sum(cleaned_image_filled_holes)


def _distance(P1, P2):
    """Finds the Euclidian distance between two pixel positions."""
    return ((P1[0] - P2[0])**2 + (P1[1] - P2[1])**2) ** 0.5


def pad_skeleton(cell_skeleton, soma_on_skeleton):
    """Adds padding to cell skeleton image."""
    # get all the pixel indices representing skeleton
    skeleton_indices = np.nonzero(cell_skeleton)

    # get corner points enclosing skeleton
    x_min, x_max = min(skeleton_indices[1]), max(skeleton_indices[1]) + 1
    y_min, y_max = min(skeleton_indices[0]), max(skeleton_indices[0]) + 1
    bounded_skeleton = cell_skeleton[y_min:y_max, x_min:x_max]

    pad_width = max(bounded_skeleton.shape)//2
    bounded_skeleton_boundary = [x_min, x_max, y_min, y_max]

    # get updated soma position on bounded and padded skeleton
    soma_on_bounded_skeleton = soma_on_skeleton[0] - \
        y_min, soma_on_skeleton[1]-x_min
    soma_on_padded_skeleton = soma_on_skeleton[0] - \
        y_min+pad_width, soma_on_skeleton[1]-x_min+pad_width

    return (
        np.pad(bounded_skeleton, pad_width=pad_width, mode='constant'),
        soma_on_padded_skeleton,
        bounded_skeleton_boundary,
        soma_on_bounded_skeleton
    )


def _cmp(branch, path):
    return (
        branch[0] == path[0]
        and branch[1] == path[-1]
        or branch[0] == path[-1]
        and branch[1] == path[0]
    )


def _eliminate_loops(branch_stats, paths_list):
    """Eliminate loops in branches."""
    loop_indices = []
    loop_branch_end_pts = []

    # set that keeps track of what elements have been added
    seen = set()
    # eliminate loops from branch statistics
    for branch_no, branch in enumerate(branch_stats):
        # If element not in seen, add it to both
        current = (branch[0], branch[1])
        if current not in seen:
            seen.add(current)
        elif current in seen:
            # for deleting the loop index from branch statistics
            loop_indices.append(branch_no)
            # for deleting paths from paths list by recognizing loop end pts
            loop_branch_end_pts.append((int(branch[0]), int(branch[1])))

    new_branch_stats = np.delete(branch_stats, loop_indices, axis=0)

    # TODO: no loops on test set
    # eliminate loops from paths list
    path_indices = []
    for loop_end_pts in loop_branch_end_pts:
        for path_no, path in enumerate(paths_list):
            if _cmp(loop_end_pts, path):
                path_indices.append(path_no)
                break

    new_paths_list = np.delete(np.array(paths_list, dtype=object),
                               path_indices, axis=0)

    return new_branch_stats, new_paths_list


def get_soma_on_skeleton(cell_image, image_type, cell_skeleton):
    """Retrieves soma's position on cell skeleton."""
    soma = _get_soma(cell_image, image_type)
    skeleton_pixel_coordinates = [(i, j) for (
        i, j), val in np.ndenumerate(cell_skeleton) if val != 0]
    soma_on_skeleton = min(skeleton_pixel_coordinates,
                           key=lambda x: _distance(soma, x))

    return soma_on_skeleton


def get_total_length(cell_skeleton):
    return np.sum(cell_skeleton)/255


def get_avg_process_thickness(surface_area, total_length):
    return round(surface_area / total_length, 1)


def get_convex_hull(cell):
    convex_hull = convex_hull_image(cell.image)
    cell.convex_hull = convex_hull

    return np.sum(convex_hull)


def get_no_of_forks(cell):
    # get the degree for every cell pixel (no. of neighbouring pixels)
    
    #degrees = skeleton_to_csgraph(cell.skeleton)[2]
    degrees = make_degree_image(cell.skeleton)[0]
    # array of all pixel locations with degree more than 2
    fork_image = np.where(degrees > [2], 1, 0)
    s = generate_binary_structure(2, 2)
    #num_forks = label(degrees>2, structure=s)[1]
    num_forks = label(make_degree_image(skeletonize(cell.image, method='lee'))>2, structure=s)[1]

    # for future plotting
    fork_indices = np.where(make_degree_image(skeletonize(cell.image, method='lee'))>2)
    cell._fork_coords = zip(fork_indices[0], fork_indices[1])
    
    return num_forks


def _branch_structure(junctions, branch_stats, paths_list):
    next_set_junctions = []
    next_set_branches = []
    term_branches = []

    for junction in junctions:
        branches_travelled = []
        for branch_no, branch in enumerate(branch_stats):
            if branch[0] == junction:
                if branch[3] == 2:
                    next_set_junctions.append(branch[1])
                    for path in paths_list:
                        if _cmp(branch, path):
                            next_set_branches.append(path)
                            branches_travelled.append(branch_no)
                if branch[3] == 1:
                    for path in paths_list:
                        if _cmp(branch, path):
                            term_branches.append(path)
                            next_set_branches.append(path)
                            branches_travelled.append(branch_no)
            elif branch[1] == junction:
                if branch[3] == 2:
                    next_set_junctions.append(branch[0])
                    for path in paths_list:
                        if _cmp(branch, path):
                            next_set_branches.append(path)
                            branches_travelled.append(branch_no)
                if branch[3] == 1:
                    for path in paths_list:
                        if _cmp(branch, path):
                            term_branches.append(path)
                            next_set_branches.append(path)
                            branches_travelled.append(branch_no)

        branch_stats = np.delete(branch_stats, branches_travelled, axis=0)

    return next_set_junctions, next_set_branches, term_branches, branch_stats


def classify_branching_structure(cell_skeleton, soma_on_skeleton):

    def _get_soma_node():
        near = []
        for i in range(Skeleton(cell_skeleton).n_paths):
            path_coords = Skeleton(
                cell_skeleton).path_coordinates(i)
            nearest = min(path_coords, key=lambda x: _distance(
                soma_on_skeleton, x))
            near.append(nearest)

        soma_on_path = min(near, key=lambda x: _distance(
            soma_on_skeleton, x))

        for i, j in enumerate(Skeleton(cell_skeleton).coordinates):
            if all(soma_on_path == j):
                soma_node = [i]
                break

        return soma_node

    def _get_soma_branches(soma_node, paths_list):
        soma_branches = []
        for path in paths_list:
            if soma_node in path:
                soma_branches.append(path)
        return soma_branches

    pixel_graph, coords = skeleton_to_csgraph(cell_skeleton)[0:2]
    branch_stats = np.array(summarize(Skeleton(cell_skeleton)))[:,1:]
    paths_list = Skeleton(cell_skeleton).paths_list()

    terminal_branches = []
    branching_structure_array = []

    # get branches containing soma node
    soma_node = _get_soma_node()
    soma_branches = _get_soma_branches(soma_node, paths_list)
    if len(soma_branches) > 2:
        junctions = soma_node
        delete_soma_branch = False
    else:
        # collect first level/primary branches
        junctions = [soma_branches[0][0], soma_branches[0][-1]]
        delete_soma_branch = True

    # eliminate loops in branches and path lists
    #branch_stats, paths_list = _eliminate_loops(branch_stats, paths_list)

    while True:
        junctions, branches, term_branch, branch_stats = _branch_structure(
            junctions, branch_stats, paths_list)
        branching_structure_array.append(branches)
        terminal_branches.extend(term_branch)
        if len(junctions) == 0:
            break

    if delete_soma_branch:
        try:
            branching_structure_array[0].remove(soma_branches[0])
        except:
            pass

    return branching_structure_array, terminal_branches, coords


def get_primary_branches(branching_struct):
    prim_branches = branching_struct[0]
    n_prim_branches = len(prim_branches)
    avg_len_of_prim_branches = 0 if n_prim_branches == 0 else sum(
        map(len, prim_branches))/float(len(prim_branches))

    return n_prim_branches, round(avg_len_of_prim_branches, 1)


def get_secondary_branches(branching_struct):
    sec_branches = [] if len(branching_struct) < 2 else branching_struct[1]

    n_sec_branches = len(sec_branches)
    avg_len_of_sec_branches = 0 if n_sec_branches == 0 else sum(
        map(len, sec_branches))/float(len(sec_branches))

    return n_sec_branches, round(avg_len_of_sec_branches, 1)


def get_tertiary_branches(branching_struct):
    tert_branches = [] if len(branching_struct) < 3 else branching_struct[2]

    n_tert_branches = len(tert_branches)
    avg_len_of_tert_branches = 0 if n_tert_branches == 0 else sum(
        map(len, tert_branches))/float(len(tert_branches))

    return n_tert_branches, round(avg_len_of_tert_branches, 1)


def get_quatenary_branches(branching_struct):
    quat_branches = [] if len(branching_struct) < 4 else branching_struct[3:]

    quat_branches = [
        branch for branch_lvl in quat_branches for branch in branch_lvl]
    n_quat_branches = len(quat_branches)
    avg_len_of_quat_branches = 0 if n_quat_branches == 0 else sum(
        map(len, quat_branches))/float(len(quat_branches))

    return n_quat_branches, round(avg_len_of_quat_branches, 1)


def get_terminal_branches(term_branches):
    n_term_branches = len(term_branches)
    avg_len_of_term_branches = 0 if n_term_branches == 0 else sum(
        map(len, term_branches))/float(len(term_branches))

    return n_term_branches, round(avg_len_of_term_branches, 1)
