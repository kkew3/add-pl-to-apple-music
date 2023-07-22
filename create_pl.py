import typing as ty
import sys
import argparse
import plistlib
from pathlib import Path
import urllib.parse
import warnings


def make_parser():
    parser = argparse.ArgumentParser(
        description=(
            'Make playlist XML from files to be imported to Apple Music app.'))
    parser.add_argument(
        '-b',
        '--basedir',
        type=Path,
        default=Path.cwd(),
        help=(
            'common base directory assumed when the music files to include is '
            'specified as relative path, default to current working directory'
        ))
    parser.add_argument(
        '-n', '--name', default='playlist', help=('the name of the playlist'))
    parser.add_argument(
        '-T',
        '--files-from',
        dest='files_from',
        metavar='FILE_LIST',
        help=('include music files from FILE_LIST (one per line) in the '
              'playlist rather than from command line; `-` means /dev/stdin'))
    parser.add_argument(
        '-W',
        '--no-warnings',
        action='store_true',
        dest='no_warnings',
        help=('suppress warnings issued upon the Internet tracks '
              'which cannot be handled by this script'))
    parser.add_argument(
        'library_xml',
        type=Path,
        help=('the library XML file exported from Apple Music app'))
    parser.add_argument(
        'output_xml', type=Path, help=('the XML path to write'))
    parser.add_argument(
        'files_to_include',
        metavar='MUSIC_FILE',
        nargs='*',
        help='the music files to include; these get ignored when `-T` '
        '(`--files-from`) is specified')
    return parser


def as_abs_path(
    basedir: Path,
    path: ty.Union[str, Path],
) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = basedir / path
    return path


def read_include_music_files(
    files_from: ty.Optional[str],
    files_to_include: ty.List[str],
) -> ty.List[str]:
    if files_from == '-':
        # read from stdin
        files_to_include = [line.rstrip('\n') for line in sys.stdin]
    elif files_from:
        # read from FILE_LIST
        with open(Path(files_from), encoding='utf-8') as infile:
            files_to_include = [line.rstrip('\n') for line in infile]
    else:
        # read from files_to_include; nothing else need to be done
        pass
    return files_to_include


def parse_library_xml(
    xmlfile: Path,
    no_warnings: bool,
) -> ty.Tuple[dict, ty.Dict[Path, dict]]:
    """
    Assume one physical file maps to at most one music item.

    :param xmlfile: the XML path to read
    :param no_warnings: whether to show warnings
    :return: the base plist, a map from music file path to track dict
    """
    with open(xmlfile, 'rb') as infile:
        plist = plistlib.load(infile)
    location_to_track_dict = {}
    for track_id, track_dict in plist['Tracks'].items():
        loc = urllib.parse.urlparse(track_dict['Location'])
        if loc.scheme != 'file':
            if not no_warnings:
                warnings.warn(
                    'Skipped parsing track id={} since it\'s not a local file'
                    .format(track_id))
            continue
        loc_path = Path(urllib.parse.unquote(loc.path))
        location_to_track_dict[loc_path] = track_dict
    del plist['Tracks']
    del plist['Playlists']
    return plist, location_to_track_dict


class PlaylistsBuilder:
    def __init__(
        self,
        basedir: Path,
        library_xml: Path,
        no_warnings: bool,
    ) -> None:
        self.basedir = basedir
        self._base_plist, self._location_to_track_dict = parse_library_xml(
            library_xml, no_warnings)
        self.playlists = {}

    def __getitem__(self, name):
        return self.playlists[name]

    def __setitem__(self, name, value):
        self.playlists[name] = value

    def build(self, output: Path) -> None:
        tracks_dict = {}
        name_to_track_ids = {}
        for name, paths in self.playlists.items():
            paths = set(as_abs_path(self.basedir, x) for x in paths)
            name_to_track_ids[name] = []
            for path, track_dict in self._location_to_track_dict.items():
                if path in paths:
                    tid = track_dict['Track ID']
                    name_to_track_ids[name].append(tid)
                    tracks_dict[str(tid)] = track_dict
        playlists_dict = [
            {
                'Name': name,
                'Description': '',
                'Playlist ID': 0,  # a placeholder
                'Playlist Persistent ID': '',
                'All Items': True,
                'Playlist Items': [{
                    'Track ID': tid
                } for tid in track_ids],
            } for name, track_ids in name_to_track_ids.items()
        ]
        self._base_plist['Tracks'] = tracks_dict
        self._base_plist['Playlists'] = playlists_dict
        with open(output, 'wb') as outfile:
            plistlib.dump(self._base_plist, outfile)


def main():
    """
    A demo of how to use `PlaylistsBuilder`.
    """
    args = make_parser().parse_args()
    bd = PlaylistsBuilder(args.basedir, args.library_xml, args.no_warnings)
    files = read_include_music_files(args.files_from, args.files_to_include)
    bd[args.name] = files
    bd.build(args.output_xml)


if __name__ == '__main__':
    main()
