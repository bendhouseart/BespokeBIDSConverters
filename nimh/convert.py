import subprocess
import pandas as pd
import sys
from os.path import isdir, isfile
from os import listdir, walk, makedirs
import pathlib


class Convert:
    def __init__(self, image_folder, metadata_path, destination_path=None, subject_id=None, session_id=None):
        self.image_folder = image_folder
        self.metadata_path = metadata_path
        self.destination_path = destination_path
        self.subject_id = subject_id
        self.session_id = session_id
        self.metadata_dataframe = None

        # if no destination path is supplied plop nifti into the same folder as the dicom images
        if not destination_path:
            self.destination_path = self.image_folder
        else:
            # make sure destination path exists
            if isdir(destination_path):
                pass
            else:
                print(f"No folder found at destination, creating folder(s) at {destination_path}")
                makedirs(destination_path)

        if self.check_for_dcm2niix() != 0:
            raise Exception("dcm2niix error:\n" +
                            "The converter relies on dcm2niix.\n" +
                            "dcm2niix was not found in path, try installing or adding to path variable.")

        # no reason not to convert the image files immediately if dcm2niix is there
        self.dcm2niix()

    @staticmethod
    def check_for_dcm2niix():
        check = subprocess.run("dcm2niix -h", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return check.returncode

    def collect_metadata(self):
        """
        Opens up a metadata file and reads it into a pandas dataframe
        :return: a pd dataframe object
        """
        # collect metadata from spreadsheet
        metadata_extension = pathlib.Path(self.metadata_path).suffix
        self.open_meta_data(metadata_extension)

        # collect other metadata from one or more dicom files that might not get picked up by dcm2niix

    def open_meta_data(self, extension):
        methods = {'excel': pd.read_excel}

        if 'xls' in extension:
            proper_method = 'excel'
        else:
            proper_method = extension

        try:
            use_me_to_read = methods.get(proper_method, None)
            self.metadata_dataframe = use_me_to_read(self.metadata_path)
        except IOError:
            print(f"Problem opening {self.metadata_path}")

    def dcm2niix(self):
        """
        Just passing some args to dcm2niix using the good ole shell
        :return:
        """
        convert = subprocess.run(f"dcm2niix -o {self.destination_path} {self.image_folder}", shell=True)
        if convert.returncode != 0:
            raise Exception("Error during image conversion from dcm to nii!")


def cli():
    # simple converter takes command line arguments <folder path> <destination path> <subject-id> <session-id>
    command_line_args = sys.argv

    if len(command_line_args) < 2:
        print("Must supply at least a folder path to arguments.")
        sys.exit(1)

    if len(command_line_args) >= 2 and isdir(command_line_args[2]):
        folder_path = command_line_args[1]
    else:
        raise FileNotFoundError(f"Folder path {command_line_args[2]} is not a valid folder/path.")
    if len(command_line_args) >= 3:
        destination_path = command_line_args[2]
    if len(command_line_args) >= 4:
        bids_subject_id = command_line_args[3]
    if len(command_line_args) >= 5:
        bids_session_id = command_line_args[4]
