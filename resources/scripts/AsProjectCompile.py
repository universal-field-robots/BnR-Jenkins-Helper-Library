"""
Description: This scipt accepts project location and compile the project with appropriate version of Automation studio project

Usage: AsProjectCompile.py "ProjectPath" "TempPath" "Outputpath"

Returns : Build result
    0 = No Errors
    1 = Warnings
    3 = Build Error

Example: c:/projects/CICD/ASHelperScripts/AsProjectCompile.py "C:/projects/CICD/MachineWVD" "C:/projects/CICD/MachineWVD/Temp" "C:/projects/CICD/MachineWVD/output"

"""

import InstalledAS
import ASProject
import os
import shutil
import sys
import argparse
import tempfile
import re
import subprocess


# Regex to match error/warning lines with file and line info
# Matches to the form <file>(<pos>) : <result> <code>: <message>
annotation_regex = re.compile(
    r'(?P<file>.*?)\((?P<pos>.*?)\).*?(?i:(?P<result>error|warning)) (?P<code>\d+).*?:(?P<message>.*)')

# Fallback regex to match "Error 2132: ..." or "Warning 1234: ..."
simple_regex = re.compile(r'.*(?i:(?P<result>error|warning)) \d*:.*')

# Line column matching regex
line_column_regex = re.compile(r'Ln: (?P<line>\d+), Col: (?P<column>\d+)')


def PrintErrorsAndWarnings(output, errors=0, warnings=0):
    # Regex to match error/warning lines with file and line info
    # Matches to the form <file>(<pos>) : <result> <code>: <message>

    for line in output:
        print(line.strip())
        matches = re.search(annotation_regex, line)
        if matches:
            result = matches.group('result').lower().strip()
            file_path = matches.group('file').strip()
            pos = matches.group('pos').strip()
            message = matches.group('message').strip()
            line_col = re.search(line_column_regex, pos)
            if line_col:
                line = line_col.group('line').strip()
                column = line_col.group('column').strip()
                print(f'::{result} file={file_path},line={line},col={column}::{message}')
            else:
                print(f'::{result} file={file_path}:: At {pos}. {message}')
            if result == 'error':
                errors += 1
            elif result == 'warning':
                warnings += 1
        else:
            # Fallback for lines that match simple regex but not annotation format
            simple_matches = re.search(simple_regex, line)
            if simple_matches:
                result = simple_matches.group('result').lower().strip()
                print(f'::{result}::{line.strip()}')
                if result == 'error':
                    errors += 1
                elif result == 'warning':
                    warnings += 1


def Compile(Project, Configuration, BuildPIP, NoClean):
    __projectPath = Project._projectDir
    __compileAsPath = InstalledAS.ASInstallPath(Project)
    __PVIpath = InstalledAS.PVIPath()
    if (__compileAsPath == ''):
        print('no compatible AS installed')
        return [['', '', 3]]

    buildResult = []
    regex = re.compile(r'Build: (\d+) error\(s\), (\d+) warning\(s\)')

    for config in Project._configurations:        
        if (Configuration == Project._configurations[config]._name) or (Configuration == 'all'):
            standard_commands = f'{os.path.join(__compileAsPath, "Bin-en", "BR.AS.Build.exe")} "{os.path.join(__projectPath, Project.projectName)}" -c {Project._configurations[config]._name} -t "{Project._configurations[config].TempDirectory()}" -o "{Project._configurations[config].BinariesDirectory()}"'
            if (NoClean == False):
                print(f'Cleaning configuration {Project._configurations[config]._name}')
                result = subprocess.run(standard_commands + ' -cleanAll', cwd=__projectPath, capture_output=True, text=True)
                print(f'Cleaning configuration {Project._configurations[config]._name} complete.')
            errors = 0
            warnings = 0
            print(f'Building configuration {Project._configurations[config]._name}.')
            with subprocess.Popen(standard_commands + ' -buildMode "Build" -buildRUCPackage', cwd=__projectPath, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as result:
                for output in result.stdout:
                    PrintErrorsAndWarnings([output], errors, warnings)
            result.wait()

            if result.returncode == 0 or result.returncode == 1:
                print(f'Building configuration {Project._configurations[config]._name} complete with {warnings} warning(s).')
            else:
                print(f'Building configuration {Project._configurations[config]._name} failed with {errors} error(s).')

            buildResult.append([Project._configurations[config]._name, result.returncode, errors, warnings])

            if (BuildPIP and (result.returncode == 0 or result.returncode == 1)):
                print(f'Creating PIP for configuration {Project._configurations[config]._name}')
                #create PIP
                pilPath = os.path.join(__projectPath, "CreatePIP.pil")
                pilContents = 'CreatePIP "' + os.path.join(__projectPath, Project._configurations[config].BinariesDirectory(), Project._configurations[config]._name, Project._configurations[config]._cpuName, 'RUCPackage', 'RUCPackage.zip') + '", "InstallMode=Consistent InstallRestriction=AllowUpdatesWithoutDataLoss KeepPVValues=1 ExecuteInitExit=0 IgnoreVersion=1 AllowDowngrade=0", "Default", "SupportLegacyAR=1", "DestinationDirectory=\'' + os.path.join(__projectPath, f"{Project._configurations[config]._name}-PIP") + '\'"'
                pilFile = open(pilPath,"w")
                pilFile.write(pilContents)
                pilFile.close()
                pviTransferPath = os.path.join(__PVIpath, 'PVI', 'Tools', 'PVITransfer', 'PVITransfer.exe')
                pipCommand = (pviTransferPath + ' -silent "' + pilPath + '"')
                result = subprocess.run(pipCommand, cwd=__projectPath, capture_output=True, text=True)
                PrintErrorsAndWarnings(result.stdout.splitlines())
                shutil.make_archive(os.path.join(__projectPath, f"{Project._configurations[config]._name}-PIP"), 'zip', os.path.join(__projectPath, f"{Project._configurations[config]._name}-PIP"))
                print(f'Creating PIP for configuration {Project._configurations[config]._name} complete.')

    return buildResult

def parse_bool(s: str) -> bool:
    try:
        return {'true': True, 'false': False}[s.lower()]
    except KeyError:
        raise argparse.ArgumentTypeError(s)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--project', help='Project Directory', dest='projectDir', required=True)
    parser.add_argument('-c', '--configuration', help='Configuration to build', dest='config', required=False, default='all')
    parser.add_argument('-w', '--maxwarnings', help='Maximum allowed warnings during build, -1 disables', dest='maxWarnings', required=False, default=-1)
    parser.add_argument('-b', '--buildpip', help='Builds the Project Installation Package', dest='BuildPIP', required=False, default=False, type=parse_bool)
    parser.add_argument('-n', '--no-clean', help='Do not clean the project before building', dest='NoClean', action='store_true')
    args = parser.parse_args()

    project = ASProject.ASProject(args.projectDir)
    results = Compile(project, args.config, args.BuildPIP, args.NoClean)
    compileResult = 0
    maxWarnings = 0
    for result in results:
        compileResult = int(result[1]) if (compileResult < int(result[1])) else compileResult
        maxWarnings = result[3] if ((result[3] > maxWarnings) and (args.maxWarnings != -1)) else maxWarnings

    sys.exit(compileResult)

if __name__ == '__main__':
    main()