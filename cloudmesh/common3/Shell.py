"""
A convenient method to execute shell commands and return their output. Note: that this method requires that the
command be completely execute before the output is returned. FOr many activities in cloudmesh this is sufficient.
"""
import sys

from cloudmesh.common.Shell import Shell as Shell2
from cloudmesh.common.console import Console
import subprocess

class Shell(Shell2):

    @classmethod
    def run(cls, command, encoding='utf-8'):
        cmd = f"{command}; exit 0"
        r = subprocess.check_output(command,
                                    stderr=subprocess.STDOUT,
                                    shell=True)
        if encoding is None or  encoding == 'utf-8':
            return str(r, 'utf-8')
        else:
            return r


    @classmethod
    def check_python(cls):
        """
        checks if the python version is supported
        :return: True if it is supported
        """
        python_version = sys.version_info[:3]

        v_string = [str(i) for i in python_version]

        if python_version[0] == 2:
            Console.error(f"You are running an unsupported version of python: {python_version}")
            Console.error("Please update to python version 3.7")
            sys.exit(1)

        elif python_version[0] == 3:

            python_version_s = '.'.join(v_string)
            if (python_version[0] == 3) and (python_version[1] >= 7) and (python_version[2] >= 0):

                Console.ok(f"You are running a supported version of python: "
                           f"{python_version_s}")
            else:
                Console.error(
                    "WARNING: You are running an unsupported version of python: {:}".format(
                        python_version_s))
                Console.error("         We recommend you update your python")

        # pip_version = pip.__version__
        python_version, pip_version = cls.get_python()

        if int(pip_version.split(".")[0]) >= 18:
            Console.ok(f"You are running a supported version of pip: {pip_version}")
        else:
            Console.error("WARNING: You are running an old version of pip: " + str(
                pip_version))
            Console.error("         We recommend you update your pip  with \n")
            Console.error("             pip install -U pip\n")


