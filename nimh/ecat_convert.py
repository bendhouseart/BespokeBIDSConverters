import nibabel
import sys
import os
from os.path import isfile
from gooey import Gooey, GooeyParser

# use gui if no arguments are supplied to command line w/ call
if len(sys.argv) >= 2:
    if '--ignore-gooey' not in sys.argv:
        sys.argv.append('--ignore-gooey')


class ConvertToNifti:
    def __init__(self, ecat_path, destination_path=None):
        """
        This class converts an ecat to a more sane file format, aka a nifti. Currently
        relies on Nibabel and only supports ecat versions 7.3.
        :param ecat_path: path to the ecat file
        :param destination_path: destination of nifti and json file, if not supplied will
        send output to ecat_path's parent direction
        """
        self.ecat_path = ecat_path
        if not destination_path:
            self.destination_path = os.path.dirname(self.ecat_path)
        else:
            self.nifti_file = destination_path
        self.ecat = None
        self.ecat_main_header = {}
        self.ecat_subheaders = []
        self.affine = None

        # load ecat file
        self.read_in_ecat()

        # populate affine, header, subheaders datastructures from ecat
        self.extract_affine()
        self.extract_header()
        self.extract_subheaders()

        # convert to nifti
        self.to_nifti()

        # will populate this at some point
        self.nifti_json_contents = {}

    def read_in_ecat(self):
        self.ecat = nibabel.ecat.load(self.ecat_path)

    def extract_affine(self):
        self.affine = self.ecat.affine.tolist()

    def extract_header(self):
        """
        Extracts header and coverts it to sane type -> dictionary
        :return: self.header_info
        """

        header_entries = [entry for entry in self.ecat.header]
        for name in header_entries:

            value = self.ecat.header[name].tolist()

            # convert to string if value is type bytes
            if type(value) is bytes and 'fill' not in name:
                try:
                    value = value.decode("utf-8")
                except UnicodeDecodeError as err:
                    print(f"Error decoding header entry {name}: {value}\n {value} is type: {type(value)}")
                    print(f"Attempting to decode {value} skipping invalid bytes.")

                    if err.reason == 'invalid start byte':
                        value = value.decode("utf-8", "ignore")
                        print(f"Decoded {self.ecat.header[name].tolist()} to {value}.")

            # skip the fill sections
            if 'fill' not in name.lower():
                self.ecat_main_header[name] = value

        return self.ecat_main_header

    def extract_subheaders(self):
        # collect subheaders
        subheaders = self.ecat.dataobj._subheader.subheaders
        for subheader in subheaders:
            holder = {}
            subheader_data = subheader.tolist()
            subheader_dtypes = subheader.dtype.descr

            for i in range(len(subheader_data)):
                holder[subheader_dtypes[i][0]] = {
                    'value': self.transform_from_bytes(subheader_data[i]),
                    'dtype': self.transform_from_bytes(subheader_dtypes[i][1])}

            self.ecat_subheaders.append(holder)

    @staticmethod
    def transform_from_bytes(bytes_like):
        if type(bytes_like) is bytes:
            try:
                return bytes_like.decode()
            except UnicodeDecodeError:
                return bytes_like
        else:
            return bytes_like

    def show_header(self):
        for entry in self.ecat.header:
            value = self.ecat.header[entry].tolist()
            if type(value) is bytes:
                try:
                    print(f"{entry}: {value.decode('utf-8')}")
                except UnicodeDecodeError:
                    print(entry, value)
            else:
                print(f"{entry}: {value}")

    def to_nifti(self):
        # check if these exist

        # image shape
        image_shape = self.ecat.shape

        # affine shape
        affine_shape = self.ecat.affine.shape

        # main image data
        main_image_data = self.ecat.get_fdata()

        # debug
        print("Debug")



        pass


@Gooey
def cli():
    parser = GooeyParser()
    parser.add_argument('ecat_path', type=str,
                        help='Path to ECAT file', widget="FileChooser")
    parser.add_argument('--show', '-s', action='store_true',
                        help="Display headers to screen/stdout.")
    parser.add_argument('--metadata_path', '-m', type=str, widget='FileChooser',
                        help='Path to session metadata file.')
    parser.add_argument('--destination_path', '-d', type=str,
                        help=
                        "Destination path to send converted imaging and metadata files to. If " +
                        "omitted defaults to using the path supplied to folder path. If destination path " +
                        "doesn't exist an attempt to create it will be made.", required=False,
                        widget="FileChooser"
                        )
    args = parser.parse_args()

    if args.ecat_path and isfile(args.ecat_path):
        converter = ConvertToNifti(ecat_path=args.ecat_path)
        converter.read_in_ecat()
        print("read in ecat file")
    else:
        raise Exception(f"Argument {args.ecat_path} is not file.")

    if args.show:
        converter.show_header()


if __name__ == "__main__":
    cli()
