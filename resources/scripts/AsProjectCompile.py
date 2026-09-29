"""
Description: This script accepts project location and compile the project with appropriate version of Automation studio project

Usage: AsProjectCompile.py --project <Project Directory> --maxwarnings <Maximum allowed warnings during build, -1 disables> --buildpip <Builds the Project Installation Package>

Returns : Build result
    0 = No Errors
    1 = Warnings
    3 = Build Error

Example: c:/AsProjectCompile.py --project "C:/projects/CICD/MachineWVD" --maxwarnings 5 --buildpip

"""

import InstalledAS
import ASProject
import os
import shutil
import sys
import argparse
import re
import subprocess


# Regex to match error/warning lines with file and line info
# Matches to the form <file>(<pos>) : <result> <code>: <message>
annotation_regex = re.compile(
    r'(?P<file>.*?)\((?P<pos>.*?)\).*?(?i:(?P<result>error|warning|security risk)) (?P<code>\d+).*?:(?P<message>.*)')

# Fallback regex to match when no failure code is present, e.g. <file>(<pos>) : <result> : <message>
fallback_regex = re.compile(
    r'(?P<file>.*?): \((?P<pos>.*?)\).*?(?i:(?P<result>error|warning|security risk)) :(?P<message>.*)')

# Fallback regex to match "Error 2132: ..." or "Warning 1234: ..."
simple_regex = re.compile(r'.*(?i:(?P<result>error|warning|security risk)) \d*:.*')

# Line column matching regex
line_column_regex = re.compile(r'Ln: (?P<line>\d+), Col: (?P<column>\d+)')

# Regex to match final build result line
finalResultRegex = re.compile(
    r'Build: (\d+) error\(s\), (\d+) security risk\(s\), (\d+) warning\(s\)')

# Class to hold configuration compilation results


class CompilationResult:
    def __init__(self, configuration_name, return_code, errors, warnings, security_risks):
        self.configuration_name = configuration_name
        self.return_code = return_code  # 0 = No Errors, 1 = Warnings, 3 = Build Error
        self.errors = errors
        self.warnings = warnings
        self.security_risks = security_risks


def PrintErrorsAndWarnings(output):
    """Prints errors and warnings in a format that GitHub Actions can recognize as annotations."""
    for line in output:
        annotation_matches = re.search(annotation_regex, line)
        fallback_matches = re.search(fallback_regex, line)
        simple_matches = re.search(simple_regex, line)
        if annotation_matches:
            result = annotation_matches.group('result').lower().strip()
            file_path = annotation_matches.group('file').strip()
            pos = annotation_matches.group('pos').strip()
            message = annotation_matches.group('message').strip()
            line_col = re.search(line_column_regex, pos)
            if line_col:
                line = line_col.group('line').strip()
                column = line_col.group('column').strip()
                print(f'::{result} file={file_path},line={line},col={column}::{message}')
            else:
                print(f'::{result} file={file_path}:: At {pos}. {message}')
        elif fallback_matches:

            result = fallback_matches.group('result').lower().strip()
            file_path = fallback_matches.group('file').strip()
            pos = fallback_matches.group('pos').strip()
            message = fallback_matches.group('message').strip()
            line_col = re.search(line_column_regex, pos)
            if line_col:
                line = line_col.group('line').strip()
                column = line_col.group('column').strip()
                print(f'::{result} file={file_path},line={line},col={column}::{message}')
            else:
                print(f'::{result} file={file_path}:: At {pos}. {message}')
        elif simple_matches:
            # Fallback for lines that match simple regex but not annotation format
            result = simple_matches.group('result').lower().strip()
            print(f'::{result}::{line.strip()}')
        else:
            # If no matches, print the line as is
            print(line.strip())


def Compile(Project: ASProject.ASProject, BuildPIP: bool) -> CompilationResult:
    """Compile the given Automation Studio project and optionally build a PIP."""
    __projectPath: str = Project._projectDir
    __compileAsPath: str = InstalledAS.ASInstallPath(Project)
    __PVIpath: str = InstalledAS.PVIPath()
    if __compileAsPath == '':
        print('no compatible AS installed')
        return CompilationResult('', 3, 0, 0, 0)  # Return error code 3 for build error

    print(f'Building configuration {Project._configurations[config]._name}.')
    with subprocess.Popen(f'{os.path.join(__compileAsPath, "Bin-en", "BR.AS.Build.exe")}  "{
            os.path.join(__projectPath, Project.projectName)} " -buildMode "Build" -buildRUCPackage', cwd=__projectPath, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as result:
        for output in result.stdout:
            PrintErrorsAndWarnings([output])
    result.wait()

    errors, security_risks, warnings = 0, 0, 0
    finalResult = finalResultRegex.search(result.stdout.read())
    if finalResult:
        errors = int(finalResult.group(1))
        security_risks = int(finalResult.group(2))
        warnings = int(finalResult.group(3))

    if result.returncode == 3:
        print(f'Building configuration {Project._configurations[config]._name} failed.')
        return CompilationResult(
            Project._configurations[config]._name, 3, errors, warnings, security_risks)

    if BuildPIP:
        print(f'Creating PIP for configuration {Project._configurations[config]._name}')
        # create PIP
        rucPackagePath = os.path.join(
            __projectPath, Project._configurations[config].BinariesDirectory(),
            Project._configurations[config]._name, Project._configurations[config]._cpuName,
            'RUCPackage', 'RUCPackage.zip')
        pipPath = os.path.join(
            __projectPath, f"{Project._configurations[config]._name}-PIP")
        pilPath = os.path.join(__projectPath, "CreatePIP.pil")
        # Create a PIP using PVITransfer
        # TODO: Check that these are the best install modes and restrictions
        pilContents = 'OfflineUpdate "' + rucPackagePath + '", "Network", "InstallMode=ForceReboot InstallRestriction=AllowInitialInstallation KeepPVValues=1 ExecuteInitExit=0 IgnoreVersion=1 AllowDowngrade=0", "Default", "DestinationDirectory=\'' + pipPath + '\'"'
        pilFile = open(pilPath, "w", encoding='utf-8')
        pilFile.write(pilContents)
        pilFile.close()
        pviTransferPath = os.path.join(
            __PVIpath, 'PVI', 'Tools', 'PVITransfer', 'PVITransfer.exe')
        pipCommand = pviTransferPath + ' -silent "' + '-consoleOutput' + pilPath + '"'
        pipResult = subprocess.run(pipCommand, cwd=__projectPath,
                                   capture_output=True, text=True, check=False)
        PrintErrorsAndWarnings(pipResult.stdout.splitlines())
        # PVITransfer reports failures in its own log rather than on stdout.
        if os.path.isdir(pipPath) == False:
            print(
                f'Creating PIP for configuration {Project._configurations[config]._name} failed.')
            return CompilationResult(
                Project._configurations[config]._name, 3, errors, warnings, security_risks)
        shutil.make_archive(os.path.join(
            __projectPath, f"{Project._configurations[config]._name}-PIP-v{Project._configurations[config]._configVersion}"), 'zip', pipPath)
        print(
            f'Creating PIP for configuration {Project._configurations[config]._name} complete.')

    return CompilationResult(
        Project._configurations[config]._name, result.returncode, errors, warnings, security_risks)


def parse_bool(s: str) -> bool:
    """Parse a string as a boolean value."""
    try:
        return {'true': True, 'false': False}[s.lower()]
    except KeyError as exc:
        raise argparse.ArgumentTypeError(s) from exc


def main() -> None:
    """Parse command-line arguments, compile the project, and set the exit code."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--project', help='Project Directory',
                        dest='projectDir', required=True)
    parser.add_argument('-w', '--maxwarnings',
                        help='Maximum allowed warnings during build, -1 disables',
                        dest='maxWarnings', required=False, default=-1)
    parser.add_argument(
        '-b', '--buildpip', help='Builds the Project Installation Package', dest='BuildPIP',
        required=False, action='store_true')
    args = parser.parse_args()

    project = ASProject.ASProject(args.projectDir)
    results = Compile(project, args.BuildPIP)
    if results.return_code == 3 or (results.warnings > args.maxWarnings and args.maxWarnings != -1):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
