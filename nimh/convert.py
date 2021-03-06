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
import platform
from numpy import cumsum
from gooey import Gooey, GooeyParser

# determine whether to run as gui or not
if len(sys.argv) >= 2:
    if '--ignore-gooey' not in sys.argv:
        sys.argv.append('--ignore-gooey')


class Convert:
    def __init__(self, image_folder, metadata_path=None, destination_path=None, subject_id=None, session_id=None):
        self.image_folder = image_folder
        self.metadata_path = metadata_path
        self.destination_path = None
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
                self.destination_path = destination_path
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
        if self.metadata_path:
            self.extract_metadata()
            # build output structures for metadata
            bespoke_data = self.bespoke()

            # assign output structures to class variables
            self.future_json = bespoke_data['future_json']
            self.future_blood_tsv = bespoke_data['future_blood_tsv']
            self.future_blood_json = bespoke_data['future_blood_json']
            self.participant_info = bespoke_data['participants_info']

        # create strings for output files
        if self.session_id:
            self.session_string = '_ses-' + self.session_id
        else:
            self.session_string = ''

        # now for subject id
        if subject_id:
            self.subject_id = subject_id
        else:
            self.subject_id = str(self.dicom_header_data.PatientName)
            # check for non-bids values
            self.subject_id = re.sub("[^a-zA-Z\d\s:]", '', self.subject_id)

        self.subject_string = 'sub-' + self.subject_id

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
                pet_json = os.path.join(self.destination_path, filepath)
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

        convert = subprocess.run(f"dcm2niix -w 1 -z y -o {self.destination_path} {self.image_folder}", shell=True,
                                 capture_output=True)
        if convert.returncode != 0 and bytes("Skipping existing file named",
                                             'utf-8') not in convert.stdout or convert.stderr:
            print(convert.stderr)
            raise Exception("Error during image conversion from dcm to nii!")

        # note dcm2niix will go through folder and look for dicoms, it will then create a nifti with a filename
        # of the folder dcm2niix was pointed at with a .nii extension. In other words it will place a .nii file with
        # the parent folder's name in the parent folder. We need to keep track of this path and possibly (most likely)
        # rename it

    def bespoke(self):

        future_json = {
            'Manufacturer': self.nifti_json_data.get('Manufacturer'),
            'ManufacturersModelName': self.nifti_json_data.get('ManufacturersModelName'),
            'Units': 'Bq/mL',
            'TracerName': self.nifti_json_data.get('Radiopharmaceutical'),  # need to grab part of this string
            'TracerRadionuclide': self.nifti_json_data.get('RadionuclideTotalDose', default=0) / 10 ** 6,
            'InjectedRadioactivityUnits': 'MBq',
            'InjectedMass': self.metadata_dataframe.iloc[35, 10] * self.metadata_dataframe.iloc[38, 6],
            # nmol/kg * weight
            'InjectedMassUnits': 'nmol',
            'MolarActivity': self.metadata_dataframe.iloc[0, 35] * 0.000037,  # uCi to GBq
            'MolarActivityUnits': 'GBq/nmol',
            'SpecificRadioactivity': 'n/a',
            'SpecificRadioactivityUnits': 'n/a',
            'ModeOfAdministration': 'bolus',
            'TimeZero': '10:15:14',
            'ScanStart': 61,
            'InjectionStart': 0,
            'FrameTimesStart':
                [int(entry) for entry in ([0] +
                                          list(cumsum(self.nifti_json_data['FrameDuration']))[
                                          0:len(self.nifti_json_data['FrameDuration']) - 1])],
            'FrameDuration': self.nifti_json_data['FrameDuration'],
            'AcquisitionMode': 'list mode',
            'ImageDecayCorrected': True,
            'ImageDecayCorrectionTime': -61,
            'ReconMethodName': self.dicom_header_data.ReconstructionMethod,
            'ReconMethodParameterLabels': ['iterations', 'subsets', 'lower energy threshold', 'upper energy threshold'],
            'ReconMethodParameterUnits': ['none', 'none', 'keV', 'keV'],
            'ReconMethodParameterValues': [
                3,
                21,
                float(min(re.findall('\d+\.\d+', str(self.dicom_header_data.EnergyWindowRangeSequence).lower()))),
                float(max(re.findall('\d+\.\d+', str(self.dicom_header_data.EnergyWindowRangeSequence).lower()))),
            ],
            'ReconFilterType': self.dicom_header_data.ConvolutionKernel,
            'ReconFilterSize': 0,
            'AttenuationCorrection': self.dicom_header_data.AttenuationCorrectionMethod,
            'DecayCorrectionFactor': self.nifti_json_data['DecayFactor']

        }

        future_blood_json = {

        }

        future_blood_tsv = {
            'time': self.metadata_dataframe.iloc[2:7, 6] * 60,  # convert minutes to seconds,
            'PlasmaRadioactivity': self.metadata_dataframe.iloc[2:7, 7] / 60,
            'WholeBloodRadioactivity': self.metadata_dataframe.iloc[2:7, 9] / 60,
            'MetaboliteParentFraction': self.metadata_dataframe.iloc[2:7, 8] / 60
        }

        participants_tsv = {
            'sub_id': [self.subject_id],
            'weight': [self.dicom_header_data.PatientWeight],
            'sex': [self.dicom_header_data.PatientSex]
        }

        return {
            'future_json': future_json,
            'future_blood_json': future_blood_json,
            'future_blood_tsv': future_blood_tsv,
            'participants_info': participants_tsv
        }

    def write_out_jsons(self, manual_path=None):
        """
        Writes out blood and modified *_pet.json file at destination path
        manual_path: a folder path specified at function cal by user, defaults none
        :return:
        """

        if manual_path is None:
            # dry
            identity_string = os.path.join(self.destination_path, self.subject_string + self.session_string)
        else:
            identity_string = os.path.join(manual_path, self.subject_string + self.session_string)

        with open(identity_string + '_pet.json', 'w') as outfile:
            json.dump(self.future_json, outfile, indent=4)

        # write out better json
        with open(identity_string + '_recording-manual-blood.json', 'w') as outfile:
            json.dump(self.future_blood_json, outfile, indent=4)

    def write_out_blood_tsv(self, manual_path=None):
        """
        Creates a blood.tsv
        manual_path:  a folder path specified at function call by user, defaults none
        :return:
        """
        if manual_path is None:
            # dry
            identity_string = os.path.join(self.destination_path, self.subject_string + self.session_string)
        else:
            identity_string = os.path.join(manual_path, self.subject_string + self.session_string)

        # make a pandas dataframe from blood data
        blood_data_df = pandas.DataFrame.from_dict(self.future_blood_tsv)
        blood_data_df.to_csv(identity_string + '_recording-manual_blood.tsv', sep='\t', index=False)

        # make a small dataframe for the participants
        participants_df = pandas.DataFrame.from_dict(self.participant_info)
        participants_df.to_csv('participants.tsv', sep='\t', index=False)


# get around dark mode issues on OSX
if platform.system() == 'Darwin':
    item_default = {
        'error_color': '#ea7878',
        'label_color': '#000000',
        'text_field_color': '#ffffff',
        'text_color': '#000000',
        'help_color': '#363636',
        'full_width': False,
        'validator': {
            'type': 'local',
            'test': 'lambda x: True',
            'message': ''
        },
        'external_validator': {
            'cmd': '',
        }
    }
else:
    item_default = None


''''@Gooey(
    dump_build_config=True,
    #program_name="Widget Demo",
    advanced=True,
    auto_start=False,
    body_bg_color='#262626',
    header_bg_color='#262626',
    footer_bg_color='#262626',
    sidebar_bg_color='#262626',
)
'''


@Gooey
def cli():
    # simple converter takes command line arguments <folder path> <destination path> <subject-id> <session-id>
    parser = GooeyParser()
    parser.add_argument('folder', type=str,
                        help="Folder path containing imaging data", widget="DirChooser", gooey_options=item_default)
    parser.add_argument('-m', '--metadata-path', type=str,
                        help="Path to metadata file for scan", widget="FileChooser",
                        gooey_options=item_default)
    parser.add_argument('-d', '--destination-path', type=str, gooey_options=item_default,
                        help=
                        "Destination path to send converted imaging and metadata files to. If " +
                        "omitted defaults to using the path supplied to folder path. If destination path " +
                        "doesn't exist an attempt to create it will be made.", required=False,
                        widget="DirChooser")
    parser.add_argument('-i', '--subject-id', type=str, gooey_options=item_default,
                        help='user supplied subject id. If left blank will use PatientName from dicom header',
                        required=False)
    parser.add_argument('-s', '--session_id', type=str, gooey_options=item_default,
                        help="User supplied session id. If left blank defaults to " +
                             "None/null and omits addition to output")

    args = parser.parse_args()

    if not isdir(args.folder):
        raise FileNotFoundError(f"{args.folder} is not a valid path")

    converter = Convert(
        image_folder=args.folder,
        metadata_path=args.metadata_path,
        destination_path=args.destination_path,
        subject_id=args.subject_id,
        session_id=args.session_id)

    # convert it all!
    converter.run_dcm2niix()
    if args.metadata_path:
        converter.bespoke()
        converter.write_out_jsons()
        converter.write_out_blood_tsv()


if __name__ == "__main__":
    cli()
