
from __future__ import division
import os
import sys
import struct
import h5py
from datetime import datetime
import time
import numpy

def hdf_to_gdf(hdf_file_directory, gdf_file_directory):

    print('Converting .gdf to .hdf file')
    if os.path.exists(gdf_file_directory):
        os.remove(gdf_file_directory)

    hdf_file = h5py.File(hdf_file_directory, 'a')
    with open(gdf_file_directory, 'wb') as gdf_file:
        gdf_file_to_hdf_file(gdf_file, hdf_file)

    gdf_file.close()
    hdf_file.close()
    print('Converting .gdf to .hdf file... Complete.')
def gdf_file_to_hdf_file(gdf_file, hdf_file):
    add_gdf_id(gdf_file)
    add_time_root_attribute(gdf_file, hdf_file)
    add_creator_name_root_attribute(gdf_file, hdf_file)
    add_dest_name_root_attribute(gdf_file, hdf_file)
    add_required_version_root_attribute(gdf_file, hdf_file)
    write_first_block(gdf_file)
    write_iteration(hdf_file, gdf_file)


def write_first_block(gdf_file):
    name = '00'
    chars_name = []
    for c in name:
        chars_name.append(c)

    for s in chars_name:
        s_pack = struct.pack('c', s.encode('ascii'))
        gdf_file.write(s_pack)


class Collect_Datasets():
    list_values_group = ['charge', 'mass']
    def __init__(self):
        self.sets = []
        self.grops_values = []
    def __call__(self, name, node):
        if isinstance(node, h5py.Dataset):
            self.sets.append(node)
        if isinstance(node, h5py.Group):
            for value in self.list_values_group:
                if value in node.name:
                    self.grops_values.append(node)
        return None



class Name_of_arrays:
    dict_datasets = {'momentum/x': 'Bx',
                     'momentum/y': 'By',
                     'momentum/z': 'Bz',
                     'position/x': 'x',
                     'position/y': 'y',
                     'position/z': 'z',
                     'id': 'ID',
                     'charge': 'charge',
                     'weighting': 'weighting',
                     'mass': 'm'}


def write_iteration(hdf_file, gdf_file):

   dict_array_names = {}
   data_group = hdf_file.get('data')
   hdf_datasets = Collect_Datasets()
   hdf_file.visititems(hdf_datasets)
   for key in hdf_datasets.sets:
       my_array = hdf_file[key.name][()]

       particles_idx = key.name.find("particles")
       if (particles_idx == -1):
           continue
       substring = key.name[particles_idx + 10: len(key.name)]
       name_of_particles_idx = substring.find("/")
       name_of_particles = substring[0 : name_of_particles_idx]
       name_of_dataset = substring[substring.find("/") + 1: len(substring)]
       dict_name = name_of_dataset
       dict_array_names[dict_name] = my_array

   for key in dict_array_names:
       array = dict_array_names[key]
       if dict_datasets.get(key) != None:
           write_double_dataset(gdf_file, dict_datasets[key], len(array), array)
def add_datasets_values(hdf_file, hdf_datasets, dict_array_names):
    for key in hdf_datasets.sets:
        my_array = hdf_file[key.name][()]
        name_of_particles, name_of_dataset = parse_group_name(key)
        if name_of_dataset != '' and name_of_particles != '':
            dict_array_names[name_of_particles, name_of_dataset] = my_array
            size_of_main_array = len(my_array)
    return size_of_main_array


def write_ascii_name(name, size, gdf_file, ascii_name):
    write_string(name, gdf_file)
    type_bin = struct.pack('i', int(1025))
    gdf_file.write(type_bin)
    size_bin = struct.pack('i', int(size))
    gdf_file.write(size_bin)
    charlist = list(ascii_name)
    type_size = str(size) + 's'
    gdf_file.write(struct.pack(type_size, ascii_name.encode('ascii')))


def write_double_dataset(gdf_file, name, size, array_dataset):
    write_string(name, gdf_file)
    type_bin = struct.pack('i', int(2051))
    gdf_file.write(type_bin)
    size_bin = struct.pack('i', int(size * 8))
    gdf_file.write(size_bin)
    type_size = str(size)  +'d'
    gdf_file.write(struct.pack(type_size, *array_dataset))


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
   gdf_id_byte = struct.pack('i', Constants.GDFID)
   gdf_file.write(gdf_id_byte)
def add_time_root_attribute(gdf_file, hdf_file):
    if  hdf_file.attrs.get('date') != None:
        time_created = hdf_file.attrs.get('date')
        decoding_name = time_created.decode('ascii', errors='ignore')
        time_format = datetime.strptime(str(decoding_name), "%Y-%m-%d %H:%M:%S %z")
        seconds = time.mktime(time_format.timetuple())
        time_created_byte = struct.pack('i', int(seconds))
        gdf_file.write(time_created_byte)


def add_creator_name_root_attribute(gdf_file, hdf_file):
    if hdf_file.attrs.get('software') != None:
        software = hdf_file.attrs.get('software')
        decode_software = software.decode('ascii', errors='ignore')
        write_string(decode_software, gdf_file)
    else:
        software = 'empty'
        write_string(software, gdf_file)


def add_dest_name_root_attribute(gdf_file, hdf_file):
    if hdf_file.attrs.get('destination') != None:
        destination = hdf_file.attrs.get('destination')
        decode_destination = destination.decode('ascii', errors='ignore')
        write_string(decode_destination, gdf_file)
    else:
        destination = 'empty'
        write_string(destination, gdf_file)


def add_required_version_root_attribute(gdf_file, hdf_file):
    add_versions('gdf_version', gdf_file, hdf_file)
    add_versions('softwareVersion', gdf_file, hdf_file)
    add_versions('destination_version', gdf_file, hdf_file)


def add_versions(name, gdf_file, hdf_file):
    major =''
    minor =''
    if hdf_file.attrs.get(name) != None:
        version = hdf_file.attrs.get(name)
        decode_version = version.decode('ascii', errors='ignore')
        point_idx = decode_version.find('.')
        if point_idx == -1:
            major = decode_version
            minor = '0'
        else:
            major = decode_version[0:point_idx - 1]
            minor = decode_version[point_idx - 1: len(decode_version) - 1]

        major_bin = struct.pack('B', int(major))
        minor_bin = struct.pack('B', int(minor))
        gdf_file.write(major_bin)
        gdf_file.write(minor_bin)
    else:
        major_bin = struct.pack('B', 0)
        minor_bin = struct.pack('B', 0)
        gdf_file.write(major_bin)
        gdf_file.write(minor_bin)


def write_string(name, gdf_file):
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


def files_from_args(file_names):
    gdf_file = ''
    hdf_file = ''
    for arg in file_names:
        if arg[-4:] == '.gdf':
            gdf_file = arg
        elif arg[-3:] == '.h5':

            hdf_file = arg
    return gdf_file, hdf_file


def converter(hdf_file, gdf_file):
    if hdf_file != '':
        if os.path.exists(hdf_file):
            if gdf_file == '':
                gdf_file = hdf_file[:-4] + '.gdf'
                print('Destination .gdf directory not specified. Defaulting to ' + gdf_file)
            else:
                gdf_file = gdf_file[:-4] + '.gdf'

            hdf_to_gdf(hdf_file, gdf_file)
        else:
            print('The .hdf file does not exist to convert to .gdf')


def main(file_names):
    gdf_path, hdf_path = files_from_args(file_names)
    converter(hdf_path, gdf_path)


if __name__ == "__main__":
    file_names = sys.argv
    main(file_names)
