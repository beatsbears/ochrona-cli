import json
import subprocess
import sys

from ochrona.exceptions import OchronaImportException
from ochrona.pypi_rest_client import PYPIAPIClient

INVALID_SPECIFIERS = {"<", ">", "!", "~"}
EQUALS_SPECIFIER = "=="


class SafeImport:
    def __init__(self, logger, client):
        self.logger = logger
        self.ochrona = client
        self.pypi = PYPIAPIClient(logger=logger)

    def install(self, package):
        """
        Calls the analysis API endpoint with a package and if it's safe, imports via pip.

        :param package: a package string with an optional version specified
        :return: bool
        """
        if self._check_package(package):
            self._install(package=package)
        else:
            self.logger.error(
                f"Import of {package} aborted due to detected vulnerabilities."
            )

    def _check_package(self, package):
        """
        Calls the analysis API endpoint with a package to see if a package is safe.

        :param package: a package string with an optional version specified
        :return: bool
        """
        if any(spec in package for spec in INVALID_SPECIFIERS):
            raise OchronaImportException(
                f"An invalid specifier was found in {package}, either specify the package without a version or pin to a single version using `name==version`."
            )
        parts = package.split(EQUALS_SPECIFIER)
        if len(parts) == 1:
            package = self._get_most_recent_version(package=package)
        vuln_results = self._parse_ochrona_results(
            self.ochrona.analyze(json.dumps({"dependencies": [package]}))
        )
        if len(vuln_results[1]) > 0:
            self.logger.info(
                f"A full list of packages that would be installed, included dependencies: {', '.join(vuln_results[0])}"
            )
            self.logger.error(
                f"""Vulerabilities found related to import:\n{''.join([self._format_vulnerability(v) for v in vuln_results[1]])}"""
            )
            return False
        self.logger.info(
            f"A full list of packages to be installed, included dependencies: {', '.join(vuln_results[0])}"
        )
        return True

    def _get_most_recent_version(self, package):
        """
        If a package does not have a version specified we will assume that the latest version
        should be used.

        :param package: a package string without a version
        :return: str
        """
        pypi_response = self.pypi.latest_version(package=package)
        if pypi_response != "":
            return f"{package}{EQUALS_SPECIFIER}{self.pypi.latest_version(package=package)}"
        else:
            self.logger.warn("Unable to reach Pypi to confirm latest version")
            return package

    def _parse_ochrona_results(self, results):
        """
        Parses Ochrona API results and outputs information regarding any confirmed vulnerabilities.
        :param results: API results
        :return: tuple<list, list> - a list of discovered vulnerabilities, a list of dependencies
        """
        return (results.get("flat_list"), results.get("confirmed_vulnerabilities"))

    def _install(self, package):
        """
        Call pip to install a package

        :param package: a package string with a version
        :return: bool
        """
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            return True
        except subprocess.CalledProcessError as ex:
            raise OchronaImportException("Error during pip install") from ex

    def _format_vulnerability(self, vulnerability):
        """
        Formats a vulnerability to a friendly output

        :param vulnerability: vulnerability results
        :return: str
        """
        return f"""\nVulnerability Detected on package to be installed!
    Package: {vulnerability.get('name')}
    ID: {vulnerability.get('cve_id')}
    Description: {vulnerability.get('description')}
    Ochrona Severity: {vulnerability.get('ochrona_severity_score')}
                """
