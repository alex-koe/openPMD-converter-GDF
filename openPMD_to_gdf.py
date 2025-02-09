"""Converter from openPMD to GPT format"""


from __future__ import division
import struct
from datetime import datetime
import time
import re
import argparse
import openpmd_api


def hdf_to_gdf(hdf_file_directory, gdf_file_directory, max_cell_size, species, grid_size):
    """ Find hdf file in hdf_file_directory, find gdf_file_directory"""

    print('Converting .gdf to .hdf file')

    default_max_cell_size = 1000000
    if gdf_file_directory == None:
        gdf_file_directory = hdf_file_directory[:-3] + '.gdf'

    if max_cell_size == None:
        max_cell_size = default_max_cell_size

    if species == None:
        species = ''

    series_hdf = openpmd_api.Series(hdf_file_directory, openpmd_api.Access.read_only)
    print('Destination .gdf directory not specified. Defaulting to ' + gdf_file_directory)

    with open(gdf_file_directory, 'wb') as gdf_file:
        hdf_file_to_gdf_file(gdf_file, series_hdf, max_cell_size, species, grid_size)


    gdf_file.close()
    print('Converting .hdf to .gdf file... Complete.')


def hdf_file_to_gdf_file(gdf_file, series_hdf, max_cell_size, species, grid_size):
    """ Convert from hdf file to gdf file """

    add_gdf_id(gdf_file)

    add_time_root_attribute(gdf_file, series_hdf)
    add_creator_name_root_attribute(gdf_file, series_hdf)
    add_dest_name_root_attribute(gdf_file, series_hdf)
    add_required_version_root_attribute(gdf_file, series_hdf)
    write_first_block(gdf_file)
    write_file(series_hdf, gdf_file, max_cell_size, species, grid_size)


def write_first_block(gdf_file):
    """ Write required empty first block """

    name = '00'
    chars_name = []
    for c in name:
        chars_name.append(c)

    for s in chars_name:
        s_pack = struct.pack('c', s.encode('ascii'))
        gdf_file.write(s_pack)


def decode_name(attribute_name):
    """ Decode name from binary """

    decoding_name = attribute_name.decode('ascii', errors='ignore')
    decoding_name = re.sub(r'\W+', '', decoding_name)
    return decoding_name


def get_particles_name(hdf_file):
    """ Get name of particles group """

    particles_name = ''
    if hdf_file.attrs.get('particlesPath') != None:
        particles_name = hdf_file.attrs.get('particlesPath')
        particles_name = decode_name(particles_name)
    else:
        particles_name = 'particles'
    return particles_name



class Name_of_arrays:
    """ Storage of datasets in h5 file """

    dict_datasets = {'momentum/x': 'Bx',
                     'momentum/y': 'By',
                     'momentum/z': 'Bz',
                     'position/x': 'x',
                     'position/y': 'y',
                     'position/z': 'z',
                     'id': 'ID',
                     'charge': 'q',
                     'weighting': 'nmacro',
                     'mass': 'm'}


class Getting_absolute_coordinates:

    def __init__(self, particle_spices, axis):
        self.unit_si_offset = particle_spices["positionOffset"][axis].unit_SI
        self.unit_si_position = particle_spices["position"][axis].unit_SI

    def __call__(self, value):
        absolute_coord = value[0] * self.unit_si_position + value[1] * self.unit_si_offset
        return absolute_coord


class Getting_absolute_momentum:

    def __init__(self, particle_spices, axis):
        self.unit_si_momentum = particle_spices["momentum"][axis].unit_SI

    def __call__(self, value):

        return value * self.unit_si_momentum


class Read_momentum:
    def __init__(self, series, particle_spices, axis):
        self.particle_spices = particle_spices
        self.series = series
        self.axis = axis

    def __call__(self, idx_start, idx_end):

        current_values = self.particle_spices["momentum"][self.axis][idx_start:idx_end]
        self.series.flush()

        return current_values


class Read_coordinate:
    def __init__(self, series, particle_spices, axis):
        self.series = series
        self.axis = axis
        self.particle_spices = particle_spices

    def __call__(self, idx_start, idx_end):

        position = self.particle_spices["position"][self.axis][idx_start:idx_end]
        offset = self.particle_spices["positionOffset"][self.axis][idx_start:idx_end]
        self.series.flush()

        result = list(zip(position, offset))
        return result


def write_scalar_dataset(gdf_file, particle_species, size_dataset, max_cell_size, name_scalar):

    if not check_item_exist(particle_species, name_scalar):
        return

    SCALAR = openpmd_api.Mesh_Record_Component.SCALAR
    mass = particle_species[name_scalar][SCALAR]
    value = mass.get_attribute("value")
    mass_unit = mass.get_attribute("unitSI")
    write_double_dataset_values(gdf_file, Name_of_arrays.dict_datasets.get(name_scalar),
                                size_dataset, value * mass_unit, max_cell_size)


def write_weight(series, gdf_file, particle_species, max_cell_size):

    name = "nmacro"
    write_dataset_header(name, gdf_file)

    SCALAR = openpmd_api.Mesh_Record_Component.SCALAR

    weights = particle_species["weighting"][SCALAR]
    size = weights.shape[0]
    size_bin = struct.pack('i', int(size * 8))
    gdf_file.write(size_bin)
    number_cells = int(size / max_cell_size)
    for i in range(1, number_cells + 1):
        idx_start = (i - 1) * max_cell_size
        idx_end = i * max_cell_size
        current_values = weights[idx_start:idx_end]
        series.flush()
        type_size = str(max_cell_size) + 'd'
        gdf_file.write(struct.pack(type_size, *current_values))

    idx_start = number_cells * max_cell_size
    idx_end = size
    current_values = weights[idx_start:idx_end]

    series.flush()

    last_cell_size = size - number_cells * max_cell_size
    type_size = str(last_cell_size) + 'd'
    gdf_file.write(struct.pack(type_size, *current_values))


def get_coordinates_size(particle_species):

    momentum_values = particle_species["position"]
    size = 0
    for value in momentum_values.items():
        size = value[1].shape[0]
    return size


def compute_r_macro(particle_species, unit_grid_spacing):

    particle_shape = particle_species.get_attribute("particleShape")
    species_grid_spacing = [i * particle_shape for i in unit_grid_spacing]
    r_macro = min(species_grid_spacing)/2. #convert_diametr to radius
    return r_macro


def write_particles_type(series, particle_species, gdf_file, max_cell_size, unit_grid_spacing):

    iterate_momentum(series, particle_species, gdf_file, max_cell_size)

    iterate_coords(series, particle_species, gdf_file, max_cell_size)
    size_dataset = get_coordinates_size(particle_species)
    write_scalar_dataset(gdf_file, particle_species, size_dataset, max_cell_size, "mass")
    write_scalar_dataset(gdf_file, particle_species, size_dataset, max_cell_size, "charge")
    write_weight(series, gdf_file, particle_species, max_cell_size)
    particle_species.get_attribute("particleShape")
    r_macro = compute_r_macro(particle_species, unit_grid_spacing)
    write_double_dataset_values(gdf_file, "rmacro", size_dataset, r_macro, max_cell_size)


def check_item_exist(particle_species, name_item):

    item_exist = False
    for value in particle_species.items():
        if value[0] == name_item:
            item_exist = True

    return item_exist


def get_field_sizes(iteration, grid_size):

    attrs = []
    for attr in iteration.meshes:
        attrs.append(attr)

    unit_grid_spacing = []
    grid_size = 1.
    if len(iteration.meshes) == 0:
        unit_grid_spacing.append(grid_size)
        return unit_grid_spacing

    first_mesh = iteration.meshes[attrs[0]]

    for i in range(0, len(first_mesh.grid_spacing)):
        unit_grid_spacing.append(first_mesh.grid_unit_SI * first_mesh.grid_spacing[i])

    return unit_grid_spacing


def all_species(series, iteration, gdf_file, max_cell_size, grid_size):

    unit_grid_spacing = get_field_sizes(iteration, grid_size)

    for name_group in iteration.particles:
        if not (check_item_exist(iteration.particles[name_group], "momentum") and
                check_item_exist(iteration.particles[name_group], "position")):
            continue

        write_ascii_name('var', len(name_group), gdf_file, name_group)
        write_particles_type(series, iteration.particles[name_group], gdf_file, max_cell_size, unit_grid_spacing)


def one_type_species(series, iteration, gdf_file, max_cell_size, species, grid_size):

    for name_group in iteration.particles:
        if name_group == species:
            if not (check_item_exist(iteration.particles[name_group], "momentum") and
                    check_item_exist(iteration.particles[name_group], "position")):
                continue
            unit_grid_spacing = get_field_sizes(iteration, grid_size)

            write_ascii_name('var', len(name_group), gdf_file, name_group)
            write_particles_type(series, iteration.particles[name_group], gdf_file, max_cell_size, unit_grid_spacing)


def write_data(series, iteration, gdf_file, max_cell_size, species, grid_size):

    time = iteration.time
    write_float('time', gdf_file, float(time))

    if species == '':
        all_species(series, iteration, gdf_file, max_cell_size, grid_size)
    else:
        one_type_species(series, iteration, gdf_file, max_cell_size, species, grid_size)


def write_file(series_hdf, gdf_file, max_cell_size, species, grid_size):
    for iteration in series_hdf.iterations:
        write_data(series_hdf, series_hdf.iterations[iteration], gdf_file, max_cell_size, species, grid_size)


def write_dataset_values(series, reading_absolute, geting_absolute_values, size, gdf_file, max_cell_size):

    number_cells = int(size / max_cell_size)
    for i in range(1, number_cells + 1):
        idx_start = (i - 1) * max_cell_size
        idx_end = i * max_cell_size
        current_values = reading_absolute(idx_start, idx_end)

        series.flush()
        absolute_values = []
        for value in current_values:
            absolute_values.append(geting_absolute_values(value))

        type_size = str(max_cell_size) + 'd'
        gdf_file.write(struct.pack(type_size, *absolute_values))

    idx_start = number_cells * max_cell_size
    idx_end = size
    current_values = reading_absolute(idx_start, idx_end)

    series.flush()
    absolute_values = []
    for value in current_values:
        absolute_values.append(geting_absolute_values(value))
    last_cell_size = size - number_cells * max_cell_size
    type_size = str(last_cell_size) + 'd'
    gdf_file.write(struct.pack(type_size, *absolute_values))


def write_block_header(value, name_vector, gdf_file):
    name_value = value[0]
    size = value[1].shape[0]
    name_dataset = str(name_vector + name_value)
    write_dataset_header(Name_of_arrays.dict_datasets.get(name_dataset), gdf_file)

    size_bin = struct.pack('i', int(size * 8))
    gdf_file.write(size_bin)


def iterate_momentum(series, particle_species, gdf_file, max_cell_size):

    name_vector = "momentum/"
    momentum_values = particle_species["momentum"]

    for value in momentum_values.items():
        write_block_header(value, name_vector, gdf_file)
        reading_momentum = Read_momentum(series, particle_species, value[0])
        getiings_absolute_momentum = Getting_absolute_momentum(particle_species, value[0])

        size = value[1].shape[0]
        write_dataset_values(series, reading_momentum, getiings_absolute_momentum, size, gdf_file, max_cell_size)


def iterate_coords(series, particle_species, gdf_file, max_cell_size):

    name_vector = "position/"
    momentum_values = particle_species["position"]

    for value in momentum_values.items():
        write_block_header(value, name_vector, gdf_file)
        size = value[1].shape[0]
        name_value = value[0]
        reading_coordinate = Read_coordinate(series, particle_species, name_value)
        getiings_absolute_momentum = Getting_absolute_coordinates(particle_species, name_value)
        write_dataset_values(series, reading_coordinate, getiings_absolute_momentum, size, gdf_file, max_cell_size)



def write_dataset(gdf_file, absolute_values):
    """" Write dataset of double values """

    size = len(absolute_values)
    size_bin = struct.pack('i', int(size * 8))
    gdf_file.write(size_bin)
    type_size = str(size) + 'd'
    gdf_file.write(struct.pack(type_size, *absolute_values))


def write_double_dataset_values(gdf_file, name, size_dataset, value, max_cell_size):
    """" Write dataset of double values """

    write_dataset_header(name, gdf_file)
    size_bin = struct.pack('i', int(size_dataset * 8))
    gdf_file.write(size_bin)

    number_cells = int(size_dataset / max_cell_size)
    for i in range(1, number_cells + 1):
        array_dataset = [value] * max_cell_size
        type_size = str(max_cell_size) + 'd'
        gdf_file.write(struct.pack(type_size, *array_dataset))

    last_cell_size = size_dataset - number_cells * max_cell_size
    array_dataset = [value] * last_cell_size
    type_size = str(last_cell_size) + 'd'
    gdf_file.write(struct.pack(type_size, *array_dataset))



def write_ascii_name(name, size, gdf_file, ascii_name):
    """ Write ascii name of value """

    write_string(name, gdf_file)
    type_bin = struct.pack('i', int(1025))
    gdf_file.write(type_bin)
    size_bin = struct.pack('i', int(size))
    gdf_file.write(size_bin)
    charlist = list(ascii_name)
    type_size = str(size) + 's'
    gdf_file.write(struct.pack(type_size, ascii_name.encode('ascii')))


def write_float(name, gdf_file, value):
    write_string(name, gdf_file)
    type_bin = struct.pack('i', int(1283))
    gdf_file.write(type_bin)
    size_bin = struct.pack('i', 8)
    gdf_file.write(size_bin)
    gdf_file.write(struct.pack('d', value))


def write_dataset_header(name, gdf_file):
    write_string(name, gdf_file)
    type_bin = struct.pack('i', int(2051))
    gdf_file.write(type_bin)


class Block_types:
    """ Block types for each type in GDF file"""

    directory = 256  # Directory entry start
    edir = 512  # Directory entry end
    single_value = 1024  # Single valued
    array = 2048  # Array
    ascii_character = int('0001', 16)  # ASCII character
    signed_long = int('0002', 16)  # Signed long
    double_type = int('0003', 16)  # Double
    no_data = int('0010', 16)  # No data


def add_gdf_id(gdf_file):
   """ Add required indefication block of gdf file"""

   gdf_id_byte = struct.pack('i', Constants.GDFID)
   gdf_file.write(gdf_id_byte)


def add_time_root_attribute(gdf_file, series_hdf):
    """ Add time of creation to root"""

    data_name = series_hdf.date
    time_format = datetime.strptime(data_name, "%Y-%m-%d %H:%M:%S %z")
    seconds = time.mktime(time_format.timetuple())
    time_created_byte = struct.pack('i', int(seconds))
    gdf_file.write(time_created_byte)


def add_creator_name_root_attribute(gdf_file, series_hdf):
    """ Add name of creator to root"""

    software = series_hdf.software
    write_string(software, gdf_file)


def add_dest_name_root_attribute(gdf_file, hdf_file):
    """ Add dest name to root attribute """

    destination = 'empty'
    write_string(destination, gdf_file)


def add_required_version_root_attribute(gdf_file, series_hdf):
    """ Write one iteration to hdf_file """

    add_versions('gdf_version', gdf_file, series_hdf, 1, 1)
    add_versions('softwareVersion', gdf_file, series_hdf, 3, 0)
    add_versions('destination_version', gdf_file, series_hdf)


def add_versions(name, gdf_file, hdf_file, major = 0, minor = 0):
    """Write version of file to gdf file"""

    major_bin = struct.pack('B', int(major))
    minor_bin = struct.pack('B', int(minor))
    gdf_file.write(major_bin)
    gdf_file.write(minor_bin)


def RepresentsInt(s):
    """Check that argument is int value"""

    try:
        int(s)
        return True
    except ValueError:
        return False


def write_string(name, gdf_file):
    """Write string value to gdf file"""

    while len(name) < Constants.GDFNAMELEN:
        name += chr(0)

    chars_name = []
    for c in name:
        chars_name.append(c)

    for s in chars_name:
        s_pack = struct.pack('c', s.encode('ascii'))
        gdf_file.write(s_pack)


class Constants:
    GDFID = 94325877
    GDFNAMELEN = 16


if __name__ == "__main__":
    """ Parse arguments from command line """

    parser = argparse.ArgumentParser(description="conversion from gdf to hdf")

    parser.add_argument("-openPMD_input", metavar='openPMD_input', type=str,
                        help="hdf file for conversion")

    parser.add_argument("-gdf", metavar='gdf_file', type=str,
                        help="result gdf file")

    parser.add_argument("-max_cell", metavar='max_cell', type=str,
                        help="result gdf file")

    parser.add_argument("-species", metavar='species', type=str,
                        help="one species to convert")

    parser.add_argument("-grid_size", metavar='grid_size', type=str,
                        help="size of grid cell in SI")

    args = parser.parse_args()

    hdf_to_gdf(args.openPMD_input, args.gdf, args.max_cell, args.species, args.grid_size)

