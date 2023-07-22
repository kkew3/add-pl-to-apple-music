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
        '-D', '--description', default='', help=('the playlist description'))
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
    basedir: Path,
    files_from: ty.Optional[str],
    files_to_include: ty.List[str],
) -> ty.List[Path]:
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
    return [as_abs_path(basedir, x) for x in files_to_include]


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


def build_tracks_dict_given_files(
    location_to_track_dict: ty.Dict[Path, dict],
    paths: ty.Iterable[Path],
) -> ty.Tuple[ty.Dict[str, dict], ty.List[int]]:
    """
    :param location_to_track_dict: the 2nd returned item of
           ``parse_library_xml``
    :param paths: the file paths in the playlist
    :return: the tracks dict, the track IDs
    """
    tracks = {}
    track_ids = []
    paths = set(paths)
    for path, track_dict in location_to_track_dict.items():
        if path in paths:
            tid = track_dict['Track ID']
            track_ids.append(tid)
            tracks[str(tid)] = track_dict
    return tracks, track_ids


def build_playlist_dict_given_track_ids(
    name: str,
    desc: str,
    track_ids: ty.List[int],
) -> ty.List[dict]:
    """
    :param name: name of the playlist
    :param desc: description of the playlist
    :param track_ids: the track IDs to include in the playlist
    :return: a singleton array whose first entry is the playlist dict
    """
    return [{
        'Name': name,
        'Description': desc,
        'Playlist ID': 0,  # a placeholder
        'Playlist Persistent ID': '',
        'All Items': True,
        'Playlist Items': [{
            'Track ID': tid
        } for tid in track_ids],
    }]


def fill_base_plist(
    base_plist: dict,
    tracks_dict: ty.Dict[str, dict],
    playlist_dict: ty.List[dict],
) -> None:
    """
    :param base_plist: the 1st returned item of ``parse_library_xml``
    :param tracks_dict: the 1st returned item of
           ``build_tracks_dict_given_files``
    :param playlist_dict: the 1st returned item of
           ``build_playlist_dict_given_track_ids``
    """
    base_plist['Tracks'] = tracks_dict
    base_plist['Playlists'] = playlist_dict


def main():
    args = make_parser().parse_args()
    music_files = read_include_music_files(args.basedir, args.files_from,
                                           args.files_to_include)
    base_plist, location_to_track_dict = parse_library_xml(
        args.library_xml, args.no_warnings)
    tracks_dict, track_ids = build_tracks_dict_given_files(
        location_to_track_dict, music_files)
    playlist_dict = build_playlist_dict_given_track_ids(
        args.name, args.description, track_ids)
    fill_base_plist(base_plist, tracks_dict, playlist_dict)
    with open(args.output_xml, 'wb') as outfile:
        plistlib.dump(base_plist, outfile)


if __name__ == '__main__':
    main()
