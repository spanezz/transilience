from __future__ import annotations
from typing import NamedTuple, List, Tuple
import stat

# Python port of coreutils lib/modechange

# The ASCII mode string is compiled into an array of 'struct
# modechange', which can then be applied to each file to be changed.
# We do this instead of re-parsing the ASCII string for each file
# because the compiled form requires less computation to use; when
# changing the mode of many files, this probably results in a
# performance gain.

# The traditional octal values corresponding to each mode bit
SUID = 0o4000
SGID = 0o2000
SVTX = 0o1000
RUSR = 0o0400
WUSR = 0o0200
XUSR = 0o0100
RGRP = 0o0040
WGRP = 0o0020
XGRP = 0o0010
ROTH = 0o0004
WOTH = 0o0002
XOTH = 0o0001
ALLM = 0o7777  # all octal mode bits


CHMOD_MODE_BITS = (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)


def octal_to_mode(octal: int) -> int:
    """
    Convert OCTAL, which uses one of the traditional octal values, to an internal
    mode_t value.
    """
    # Help the compiler optimize the usual case where mode_t uses the
    # traditional octal representation.
    if (stat.S_ISUID == SUID and stat.S_ISGID == SGID and stat.S_ISVTX == SVTX
            and stat.S_IRUSR == RUSR and stat.S_IWUSR == WUSR and stat.S_IXUSR == XUSR
            and stat.S_IRGRP == RGRP and stat.S_IWGRP == WGRP and stat.S_IXGRP == XGRP
            and stat.S_IROTH == ROTH and stat.S_IWOTH == WOTH and stat.S_IXOTH == XOTH):
        return octal
    else:
        return (
                (stat.S_ISUID if octal & SUID else 0) |
                (stat.S_ISGID if octal & SGID else 0) |
                (stat.S_ISVTX if octal & SVTX else 0) |
                (stat.S_IRUSR if octal & RUSR else 0) |
                (stat.S_IWUSR if octal & WUSR else 0) |
                (stat.S_IXUSR if octal & XUSR else 0) |
                (stat.S_IRGRP if octal & RGRP else 0) |
                (stat.S_IWGRP if octal & WGRP else 0) |
                (stat.S_IXGRP if octal & XGRP else 0) |
                (stat.S_IROTH if octal & ROTH else 0) |
                (stat.S_IWOTH if octal & WOTH else 0) |
                (stat.S_IXOTH if octal & XOTH else 0))


# Special operations flags.

# For the sentinel at the end of the mode changes array.
MODE_DONE = 0

# The typical case.
MODE_ORDINARY_CHANGE = 1

# In addition to the typical case, affect the execute bits if at least one
# execute bit is set already, or if the file is a directory.
MODE_X_IF_ANY_X = 2

# Instead of the typical case, copy some existing permissions for u, g, or o
# onto the other two.  Which of u, g, or o is copied is determined by which
# bits are set in the 'value' field.
MODE_COPY_EXISTING = 3


class ModeChange(NamedTuple):
    """
    Description of a mode change.
    """
    # Original group that was parsed
    group: str

    # One of "=+-"
    op: str

    # Special operations flag
    flag: int

    # Set for u, g, o, or a.
    affected: int

    # Bits to add/remove.
    value: int

    # Bits explicitly mentioned.
    mentioned: int

    def __str__(self):
        return f"{self.group}→{self.op}[{self.flag}]0o{self.affected:o}←0o{self.value:o}:0o{self.mentioned:o}"

    @classmethod
    def make_node_op_equals(cls, new_mode: int, mentioned: int) -> "ModeChange":
        """
        Return a mode_change array with the specified "=ddd"-style
        mode change operation, where NEW_MODE is "ddd" and MENTIONED
        contains the bits explicitly mentioned in the mode are MENTIONED.
        """
        return cls(
                f"0{new_mode:o}",
                op='=',
                flag=MODE_ORDINARY_CHANGE,
                affected=CHMOD_MODE_BITS,
                value=new_mode,
                mentioned=mentioned)

    @classmethod
    def compile_group(cls, group: str) -> "ModeChange":
        """
        Compile just one of the comma-separated groups
        """
        #    [ugoa]*([-+=]([rwxXst]*|[ugo]))+
        #  | [-+=][0-7]+
        p = group
        # TODO: index the string instead of popping it
        while p:
            # Which bits in the mode are operated on.
            affected = 0

            while p:
                c = p[0]
                p = p[1:]
                if c == 'u':
                    affected |= stat.S_ISUID | stat.S_IRWXU
                elif c == 'g':
                    affected |= stat.S_ISGID | stat.S_IRWXG
                elif c == 'o':
                    affected |= stat.S_ISVTX | stat.S_IRWXO
                elif c == 'a':
                    affected |= CHMOD_MODE_BITS
                elif c in "=+-":
                    op = c
                    break
                else:
                    raise ValueError(f"invalid mode: {group!r}")

            mentioned = 0
            flag = MODE_ORDINARY_CHANGE
            value = 0
            while p:
                c = p[0]

                if c in "01234567":
                    octal_mode = int(p, 8)

                    if affected:
                        raise ValueError(f"invalid mode: {group!r}")
                    affected = mentioned = CHMOD_MODE_BITS
                    value = octal_to_mode(octal_mode)
                    flag = MODE_ORDINARY_CHANGE
                    p = ""
                    break
                elif c == 'u':
                    # Set the affected bits to the value of the "u" bits on the same file.
                    value = stat.S_IRWXU
                    flag = MODE_COPY_EXISTING
                    p = p[1:]
                elif c == 'g':
                    # Set the affected bits to the value of the "g" bits on the same file.
                    value = stat.S_IRWXG
                    flag = MODE_COPY_EXISTING
                    p = p[1:]
                elif c == 'o':
                    # Set the affected bits to the value of the "o" bits on
                    # the same file.
                    value = stat.S_IRWXO
                    flag = MODE_COPY_EXISTING
                    p = p[1:]
                else:
                    flag = MODE_ORDINARY_CHANGE
                    while p:
                        c = p[0]
                        p = p[1:]
                        if c == 'r':
                            value |= stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
                        elif c == 'w':
                            value |= stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
                        elif c == 'x':
                            value |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                        elif c == 'X':
                            flag = MODE_X_IF_ANY_X
                        elif c == 's':
                            # Set the setuid/gid bits if 'u' or 'g' is selected.
                            value |= stat.S_ISUID | stat.S_ISGID
                        elif c == 't':
                            # Set the "save text image" bit if 'o' is selected.
                            value |= stat.S_ISVTX
                        else:
                            break
        return cls(
                group=group,
                op=op,
                flag=flag,
                affected=affected,
                value=value,
                mentioned=(mentioned if mentioned else (
                    affected if affected else value)))

    @classmethod
    def compile(cls, mode_string: str) -> List["ModeChange"]:
        """
        Return a pointer to an array of file mode change operations created
        from MODE_STRING, an ASCII string that contains either an octal number
        specifying an absolute mode, or symbolic mode change operations with
        the form: ``[ugoa...][[+-=][rwxXstugo...]...][,...]``

        Raise ValueError if 'mode_string' does not contain a valid
        representation of file mode change operations.
        """
        if mode_string[0].isdigit():
            octal_mode = int(mode_string, 8)
            if octal_mode > ALLM:
                raise ValueError(f"invalid octal mode: {mode_string!r}")

            mode = octal_to_mode(octal_mode)
            if len(mode_string) < 5:
                mentioned = ((mode & (stat.S_ISUID | stat.S_ISGID)) |
                             stat.S_ISVTX | stat.S_IRWXU | stat.S_IRWXG |
                             stat.S_IRWXO)
            else:
                mentioned = CHMOD_MODE_BITS
            return [cls.make_node_op_equals(mode, mentioned)]

        # One loop iteration for each
        #     [ugoa]*([-+=]([rwxXst]*|[ugo]))+
        #   | [-+=][0-7]+
        compiled = []
        for group in mode_string.split(","):
            if not group:
                raise ValueError(f"invalid octal mode: {mode_string!r}")
            compiled.append(cls.compile_group(group))

        return compiled

    @classmethod
    def adjust(cls, oldmode: int, is_dir: bool, umask_value: int, changes: List["ModeChange"]) -> Tuple[int, int]:
        """
        Return the file mode bits of OLDMODE (which is the mode of a
        directory if DIR), assuming the umask is UMASK_VALUE, adjusted as
        indicated by the list of change operations CHANGES.  If DIR, the
        type 'X' change affects the returned value even if no execute bits
        were set in OLDMODE, and set user and group ID bits are preserved
        unless CHANGES mentioned them.  If PMODE_BITS is not null, store into
        *PMODE_BITS a mask denoting file mode bits that are affected by
        CHANGES.

        The returned value and *PMODE_BITS contain only file mode bits.
        For example, they have the S_IFMT bits cleared on a standard
        Unix-like host.

        Returns: newmode, pmode_bits
        """
        # The adjusted mode.
        newmode = oldmode & CHMOD_MODE_BITS

        # File mode bits that CHANGES cares about.
        mode_bits = 0

        for change in changes:
            affected = change.affected
            omit_change = (stat.S_ISUID | stat.S_ISGID if is_dir else 0) & ~ change.mentioned
            value = change.value

            if change.flag == MODE_ORDINARY_CHANGE:
                pass
            elif change.flag == MODE_COPY_EXISTING:
                # Isolate in 'value' the bits in 'newmode' to copy.
                value &= newmode

                # Copy the isolated bits to the other two parts.
                value |= (
                        (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
                            if value & (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH) else 0) |
                        (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
                            if value & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) else 0) |
                        (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                            if value & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) else 0)
                )
            elif change.flag == MODE_X_IF_ANY_X:
                # Affect the execute bits if execute bits are already set or if the
                # file is a directory.
                if (newmode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)) or is_dir:
                    value |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

                # If WHO was specified, limit the change to the affected bits.
                # Otherwise, apply the umask.  Either way, omit changes as
                # requested.
                value &= (affected if affected else ~umask_value) & ~ omit_change

            # If WHO was specified, limit the change to the affected bits.
            # Otherwise, apply the umask.  Either way, omit changes as
            # requested.
            value &= (affected if affected else ~umask_value) & ~ omit_change

            if change.op == '=':
                # If WHO was specified, preserve the previous values of bits that
                # are not affected by this change operation. Otherwise, clear all
                # the bits.
                preserved = (~affected if affected else 0) | omit_change
                mode_bits |= CHMOD_MODE_BITS & ~preserved
                newmode = (newmode & preserved) | value
            elif change.op == '+':
                mode_bits |= value
                newmode |= value
            elif change.op == '-':
                mode_bits |= value
                newmode &= ~value

        return newmode, mode_bits
