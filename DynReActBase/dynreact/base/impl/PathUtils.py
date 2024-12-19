import re


class PathUtils:

    # Match non-(alphanumeric or dot)
    # https://stackoverflow.com/questions/469913/regular-expressions-is-there-an-and-operator
    _pattern = r"(?=\W)([^.])"
    _pattern_compiled = re.compile(_pattern)

    @staticmethod
    def to_valid_filename(input: str) -> str:
        """
        Uses a whitelist based approach to generate filenames, allowing unicode characters, underscore and dots
        :param input:
        :return:
        """
        return re.sub(PathUtils._pattern_compiled, "_", input)
