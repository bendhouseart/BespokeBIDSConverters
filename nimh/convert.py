import os.path
import subprocess

import pandas
import pandas as pd
import sys
from os.path import isdir, isfile
from os import listdir, walk, makedirs
import pathlib
import json
import pydicom
import re
from numpy import cumsum

required_bids_fields = {
    "Manufacturer": {"location": "pet_json", "alias": None, "value": None},
    "ManufacturersModelName": {"location": "pet_json", "alias": None, "value": None},
    "Units": {"location": "pet_json", "alias": None, "value": "Bq/mL"},
    "TracerName": {"location": "pet_json", "alias": "Radiopharmaceutical", "position": {"start": 4, "end": -1}},
    "TracerRadioNuclide": {"location": "pet_json", "alias": "Radiopharmaceutical", "position": {"start": 1, "end": 3}},
    "InjectedRadioactivity": {"location": "pet_json", "alias": "RadionuclideTotalDose", "convert": {"units": "Bq to MBQ", "factor": 1/(10**6)}},
}


class Convert:
    def __init__(self, image_folder, metadata_path, destination_path=None, subject_id=None, session_id=None):
        self.image_folder = image_folder
        self.metadata_path = metadata_path
        self.destination_path = destination_path
        self.subject_id = subject_id
        self.session_id = session_id
        self.metadata_dataframe = None  # dataframe object of text file metadata
        self.dicom_header_data = None  # extracted data from dicom header
        self.nifti_json_data = None  # extracted data from dcm2niix generated json file

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
        self.run_dcm2niix()

        # extract all metadata
        self.extract_dicom_header()
        self.extract_nifti_json()
        self.extract_metadata()

    @staticmethod
    def check_for_dcm2niix():
        check = subprocess.run("dcm2niix -h", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return check.returncode

    def extract_dicom_header(self, additional_fields=[]):
        """
        Opening up files till a dicom is located, then extracting any header information
        to be used during and after the conversion process. This includes patient/subject id,
        as well any additional frame or metadata that's required for
        :return:
        """

        for root, dirs, files in os.walk(self.image_folder):
            for f in files:
                try:
                    dicom_header = pydicom.dcmread(os.path.join(root, f))

                    # collect subject/patient id if none is supplied
                    if self.subject_id is None:
                        self.subject_id = dicom_header.PatientID

                    self.dicom_header_data = dicom_header
                    break

                except pydicom.errors.InvalidDicomError:
                    pass

    def extract_nifti_json(self):
        """
        Collects the information contained in the wanted information list and adds it to self.
        :return:
        """

        # look for nifti json in destination folder
        pet_json = None
        collect_contents = listdir(self.destination_path)
        for filepath in collect_contents:
            if ".json" in filepath:
                pet_json = filepath
                break
            else:
                for root, dirs, files in os.walk(self.destination_path):
                    for f in files:
                        if ".json" in f:
                            pet_json = os.path.join(root, f)
                            break

        if pet_json is None:
            raise Exception("Unable to find json file for nifti image")

        with open(pet_json, 'r') as infile:
            self.nifti_json_data = json.load(infile)

    def extract_metadata(self):
        """
        Opens up a metadata file and reads it into a pandas dataframe
        :return: a pd dataframe object
        """
        # collect metadata from spreadsheet
        metadata_extension = pathlib.Path(self.metadata_path).suffix
        self.open_meta_data(metadata_extension)

    def open_meta_data(self, extension):
        methods = {'excel': pd.read_excel}

        if 'xls' in extension:
            proper_method = 'excel'
        else:
            proper_method = extension

        try:
            use_me_to_read = methods.get(proper_method, None)
            self.metadata_dataframe = use_me_to_read(self.metadata_path)
        except IOError as err:
            raise err(f"Problem opening {self.metadata_path}")

    def run_dcm2niix(self):
        """
        Just passing some args to dcm2niix using the good ole shell
        :return:
        """

        convert = subprocess.run(f"dcm2niix -w 0 -o {self.destination_path} {self.image_folder}", shell=True, capture_output=True)
        if convert.returncode != 0 and bytes("Skipping existing file named", 'utf-8') not in convert.stdout or convert.stderr:
            raise Exception("Error during image conversion from dcm to nii!")

        # note dcm2niix will go through folder and look for dicoms, it will then create a nifti with a filename
        # of the folder dcm2niix was pointed at with a .nii extension. In other words it will place a .nii file with
        # the parent folder's name in the parent folder. We need to keep track of this path and possibly (most likely)
        # rename it

    def bespoke(self):

        future_json = {
            'Manufacturer': self.nifti_json_data['Manufacturer'],
            'ManufacturersModelName': self.nifti_json_data['ManufacturersModelName'],
            'Units': 'Bq/mL',
            'TracerName': self.nifti_json_data['Radiopharmaceutical'],  # need to grab part of this string
            'TracerRadionuclide': self.nifti_json_data['RadionuclideTotalDose']/10**6,
            'InjectedRadioactivityUnits': 'MBq',
            'InjectedMass': self.metadata_dataframe.iloc[35, 10]*self.metadata_dataframe.iloc[38, 6],  # nmol/kg * weight
            'InjectedMassUnits': 'nmol',
            'MolarActivity': self.metadata_dataframe.iloc[0, 35]*0.000037,  # uCi to GBq
            'MolarActivityUnits': 'GBq/nmol',
            'SpecificRadioactivity': 'n/a',
            'SpecificRadioactivityUnits': 'n/a',
            'ModeOfAdministration': 'bolus',
            'TimeZero': '10:15:14',
            'ScanStart': 61,
            'InjectionStart': 0,
            'FrameTimesStart':
                [0] +
                list(cumsum(self.nifti_json_data['FrameDuration']))[0:len(self.nifti_json_data['FrameDuration']) - 1],
            'FrameDuration': self.nifti_json_data['FrameDuration'],
            'AcquisitionMode': 'list mode',
            'ImageDecayCorrected': True,
            'ImageDecayCorrectionTime': -61,
            'ReconMethodName': self.dicom_header_data.ReconstructionMethod,
            'ReconMethodParameterLabels': ['iterations', 'subsets', 'lower energy threshold', 'upper energy threshold'],
            'ReconMethodParameterUnits': ['none', 'none', 'keV', 'keV'],
            'ReconMethodParameterValues': [
                float(min(re.findall('\d+\.\d+', str(self.dicom_header_data.EnergyWindowRangeSequence).lower()))),
                float(max(re.findall('\d+\.\d+', str(self.dicom_header_data.EnergyWindowRangeSequence).lower()))),
            ],
            'ReconFilterType': self.dicom_header_data.ConvolutionKernel,
            'ReconFilterSize': 0,
            'AttenuationCorrection': self.dicom_header_data.AttenuationCorrectionMethod,
            'DecayCorrectionFactor': self.nifti_json_data['DecayFactor']
        }

        return future_json


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


if __name__ == "__main__":
    cli()
