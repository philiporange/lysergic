"""
Metadata extraction system for media files.

This module provides a pluggable extractor registry for extracting metadata
from various media file formats including audio, video, and ebooks. All
extractors are optional and gracefully degrade when their dependencies
are not available.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any, Iterable, List, Tuple


class BaseExtractor:
    """Strategy interface for a metadata extractor."""

    name: str = "base"

    def supports(self, path: Path, ext: str, mime: Optional[str]) -> bool:
        """Check if this extractor can handle the given file."""
        raise NotImplementedError

    def extract(self, path: Path) -> Optional[Dict[str, Any]]:
        """Return normalized 'media_tags' dict or None."""
        raise NotImplementedError


class ExtractorRegistry:
    """Registry for managing and coordinating metadata extractors."""

    def __init__(self, extractors: Iterable[BaseExtractor]):
        self._extractors: List[BaseExtractor] = list(extractors)

    def extract(
        self, path: Path, ext: str, mime: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Try each extractor until one succeeds or all fail."""
        for ex in self._extractors:
            try:
                if ex.supports(path, ext, mime):
                    data = ex.extract(path)
                    if data:
                        return data
            except Exception:
                # Intentionally swallow extractor-specific errors to keep
                # scanning robust
                continue
        return None


def _norm_track_disc(pair: Any) -> Tuple[Optional[int], Optional[int]]:
    """
    Normalize track/disc notation from various formats.
    Accepts '3/12', (3,12), or 3 → (3, 12|None).
    """
    if pair is None:
        return (None, None)

    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
        try:
            return (int(pair[0]), int(pair[1]) if pair[1] else None)
        except (ValueError, TypeError):
            return (None, None)

    if isinstance(pair, str) and "/" in pair:
        try:
            parts = pair.split("/")
            return (
                int(parts[0]),
                int(parts[1]) if len(parts) > 1 and parts[1] else None,
            )
        except (ValueError, IndexError):
            return (None, None)

    try:
        return (int(pair), None)
    except (ValueError, TypeError):
        return (None, None)


class MutagenAudioExtractor(BaseExtractor):
    """
    MP3/ID3, MP4/M4A/M4B, FLAC/OGG/Opus, APE, WAV (RIFF).
    Activated only if 'mutagen' is importable.
    """

    name = "mutagen"

    def __init__(self):
        try:
            import mutagen  # noqa: F401

            self._ok = True
        except ImportError:
            self._ok = False

    def supports(self, path: Path, ext: str, mime: Optional[str]) -> bool:
        if not self._ok:
            return False
        return ext in {
            "mp3",
            "m4a",
            "m4b",
            "mp4",
            "flac",
            "ogg",
            "opus",
            "ape",
            "wav",
            "mov",
        }

    def extract(self, path: Path) -> Optional[Dict[str, Any]]:
        if not self._ok:
            return None

        try:
            import mutagen

            f = mutagen.File(str(path))
            if f is None:
                return None

            # Determine container and tag format
            container = path.suffix.lower().lstrip(".")
            tag_format = self._detect_tag_format(f)

            # Extract normalized fields
            fields = {}

            # Common fields mapping
            if hasattr(f, "tags") and f.tags:
                fields = self._extract_fields(f.tags, tag_format)

            # Duration
            duration_ms = None
            if (
                hasattr(f, "info")
                and hasattr(f.info, "length")
                and f.info.length
            ):
                duration_ms = int(f.info.length * 1000)

            # Cover art detection
            has_cover_art = self._has_cover_art(f, tag_format)

            # Chapters detection
            chapters = self._count_chapters(f, tag_format)

            result = {
                "container": container,
                "tag_format": tag_format,
                "fields": fields,
            }

            if duration_ms is not None:
                result["duration_ms"] = duration_ms
            if chapters is not None:
                result["chapters"] = chapters
            if has_cover_art is not None:
                result["has_cover_art"] = has_cover_art

            return result

        except Exception:
            return None

    def _detect_tag_format(self, f) -> str:
        """Detect the tag format used in the file."""
        class_name = f.__class__.__name__.lower()

        if "id3" in class_name or "mp3" in class_name:
            return "id3"
        elif "mp4" in class_name or "m4a" in class_name:
            return "mp4"
        elif "flac" in class_name:
            return "vorbis"  # FLAC uses Vorbis comments
        elif "ogg" in class_name or "opus" in class_name:
            return "vorbis"
        elif "ape" in class_name:
            return "ape"
        elif "wave" in class_name or "riff" in class_name:
            return "riff"
        else:
            return "unknown"

    def _extract_fields(self, tags, tag_format: str) -> Dict[str, Any]:
        """Extract and normalize common metadata fields."""
        fields = {}

        if tag_format == "id3":
            fields.update(self._extract_id3_fields(tags))
        elif tag_format == "mp4":
            fields.update(self._extract_mp4_fields(tags))
        elif tag_format == "vorbis":
            fields.update(self._extract_vorbis_fields(tags))
        elif tag_format == "ape":
            fields.update(self._extract_ape_fields(tags))
        elif tag_format == "riff":
            fields.update(self._extract_riff_fields(tags))

        return fields

    def _extract_id3_fields(self, tags) -> Dict[str, Any]:
        """Extract fields from ID3 tags."""
        fields = {}

        # Text frames
        text_mappings = {
            "TIT2": "title",
            "TPE1": "artist",
            "TALB": "album",
            "TPE2": "album_artist",
            "TCON": "genre",
            "TDRC": "date",  # Recording date
            "TORY": "date",  # Original release year
            "TYER": "date",  # Year
            "TLAN": "language",
            "TPUB": "publisher",
        }

        for frame_id, field_name in text_mappings.items():
            if frame_id in tags:
                value = (
                    str(tags[frame_id].text[0])
                    if tags[frame_id].text
                    else None
                )
                if value:
                    fields[field_name] = value

        # Track number
        if "TRCK" in tags and tags["TRCK"].text:
            track, track_total = _norm_track_disc(tags["TRCK"].text[0])
            if track is not None:
                fields["track"] = track
            if track_total is not None:
                fields["track_total"] = track_total

        # Disc number
        if "TPOS" in tags and tags["TPOS"].text:
            disc, disc_total = _norm_track_disc(tags["TPOS"].text[0])
            if disc is not None:
                fields["disc"] = disc
            if disc_total is not None:
                fields["disc_total"] = disc_total

        return fields

    def _extract_mp4_fields(self, tags) -> Dict[str, Any]:
        """Extract fields from MP4 atom tags."""
        fields = {}

        # MP4 atom mappings
        atom_mappings = {
            "\xa9nam": "title",
            "\xa9ART": "artist",
            "\xa9alb": "album",
            "aART": "album_artist",
            "\xa9gen": "genre",
            "\xa9day": "date",
            "\xa9lyr": "lyrics",
            "\xa9too": "encoder",
            "\xa9wrt": "composer",
        }

        for atom, field_name in atom_mappings.items():
            if atom in tags:
                value = tags[atom][0] if tags[atom] else None
                if value:
                    fields[field_name] = str(value)

        # Track number
        if "trkn" in tags and tags["trkn"]:
            track_data = tags["trkn"][0]
            if isinstance(track_data, (list, tuple)) and len(track_data) >= 2:
                fields["track"] = track_data[0]
                if track_data[1]:
                    fields["track_total"] = track_data[1]

        # Disc number
        if "disk" in tags and tags["disk"]:
            disc_data = tags["disk"][0]
            if isinstance(disc_data, (list, tuple)) and len(disc_data) >= 2:
                fields["disc"] = disc_data[0]
                if disc_data[1]:
                    fields["disc_total"] = disc_data[1]

        return fields

    def _extract_vorbis_fields(self, tags) -> Dict[str, Any]:
        """Extract fields from Vorbis comments (FLAC/OGG)."""
        fields = {}

        # Vorbis comment mappings
        vorbis_mappings = {
            "TITLE": "title",
            "ARTIST": "artist",
            "ALBUM": "album",
            "ALBUMARTIST": "album_artist",
            "GENRE": "genre",
            "DATE": "date",
            "TRACKNUMBER": "track",
            "TRACKTOTAL": "track_total",
            "DISCNUMBER": "disc",
            "DISCTOTAL": "disc_total",
            "LANGUAGE": "language",
            "PUBLISHER": "publisher",
        }

        for vorbis_key, field_name in vorbis_mappings.items():
            if vorbis_key in tags:
                value = tags[vorbis_key][0] if tags[vorbis_key] else None
                if value:
                    if field_name in [
                        "track",
                        "track_total",
                        "disc",
                        "disc_total",
                    ]:
                        try:
                            fields[field_name] = int(value)
                        except ValueError:
                            pass
                    else:
                        fields[field_name] = str(value)

        return fields

    def _extract_ape_fields(self, tags) -> Dict[str, Any]:
        """Extract fields from APE tags."""
        # APE tags are similar to Vorbis comments in structure
        return self._extract_vorbis_fields(tags)

    def _extract_riff_fields(self, tags) -> Dict[str, Any]:
        """Extract fields from RIFF/WAV INFO chunk."""
        fields = {}

        # RIFF INFO mappings
        riff_mappings = {
            "INAM": "title",
            "IART": "artist",
            "IPRD": "album",
            "IGNR": "genre",
            "ICRD": "date",
            "ICMT": "comment",
        }

        for riff_key, field_name in riff_mappings.items():
            if riff_key in tags:
                value = tags[riff_key][0] if tags[riff_key] else None
                if value:
                    fields[field_name] = str(value)

        return fields

    def _has_cover_art(self, f, tag_format: str) -> Optional[bool]:
        """Detect if the file has embedded cover art."""
        try:
            if tag_format == "id3" and hasattr(f, "tags") and f.tags:
                # Look for APIC frames
                for key in f.tags.keys():
                    if key.startswith("APIC"):
                        return True
            elif tag_format == "mp4" and hasattr(f, "tags") and f.tags:
                # Look for covr atom
                return "covr" in f.tags and bool(f.tags["covr"])
            elif tag_format == "vorbis" and hasattr(f, "tags") and f.tags:
                # Look for METADATA_BLOCK_PICTURE
                return "METADATA_BLOCK_PICTURE" in f.tags
        except Exception:
            pass

        return None

    def _count_chapters(self, f, tag_format: str) -> Optional[int]:
        """Count chapters if present."""
        try:
            if tag_format == "id3" and hasattr(f, "tags") and f.tags:
                # Count CHAP frames
                chap_count = sum(
                    1 for key in f.tags.keys() if key.startswith("CHAP")
                )
                return chap_count if chap_count > 0 else None
            elif tag_format == "mp4" and hasattr(f, "tags") and f.tags:
                # MP4 chapter detection is more complex, skip for now
                pass
        except Exception:
            pass

        return None


class MediaInfoVideoExtractor(BaseExtractor):
    """
    MKV tags + useful video properties (duration, dimensions).
    Activated only if 'pymediainfo' is importable.
    """

    name = "mediainfo"

    def __init__(self):
        try:
            from pymediainfo import MediaInfo  # noqa: F401

            self._ok = True
        except ImportError:
            self._ok = False

    def supports(self, path: Path, ext: str, mime: Optional[str]) -> bool:
        if not self._ok:
            return False
        # Focus on MKV primarily; MediaInfo can enrich MP4/MOV too
        return ext in {"mkv", "mp4", "mov"}

    def extract(self, path: Path) -> Optional[Dict[str, Any]]:
        if not self._ok:
            return None

        try:
            from pymediainfo import MediaInfo

            mi = MediaInfo.parse(str(path))
            if not mi or not mi.tracks:
                return None

            general = next(
                (t for t in mi.tracks if t.track_type == "General"), None
            )
            # video = next(
            #     (t for t in mi.tracks if t.track_type == "Video"), None
            # )

            if not general:
                return None

            container = path.suffix.lower().lstrip(".")
            tag_format = "matroska" if container == "mkv" else "mp4"

            fields = {}

            # Extract common metadata
            if hasattr(general, "title") and general.title:
                fields["title"] = general.title
            if hasattr(general, "album") and general.album:
                fields["album"] = general.album
            if hasattr(general, "performer") and general.performer:
                fields["artist"] = general.performer
            if hasattr(general, "genre") and general.genre:
                fields["genre"] = general.genre
            if hasattr(general, "recorded_date") and general.recorded_date:
                fields["date"] = general.recorded_date

            result = {
                "container": container,
                "tag_format": tag_format,
                "fields": fields,
            }

            # Duration
            if hasattr(general, "duration") and general.duration:
                result["duration_ms"] = int(general.duration)

            return result

        except Exception:
            return None


class EpubExtractor(BaseExtractor):
    """
    EPUB OPF metadata via ebooklib. Activated only if 'ebooklib' is importable.
    """

    name = "epub"

    def __init__(self):
        try:
            import ebooklib  # noqa: F401

            self._ok = True
        except ImportError:
            self._ok = False

    def supports(self, path: Path, ext: str, mime: Optional[str]) -> bool:
        return self._ok and ext == "epub"

    def extract(self, path: Path) -> Optional[Dict[str, Any]]:
        if not self._ok:
            return None

        try:
            from ebooklib import epub

            book = epub.read_epub(str(path))
            if not book:
                return None

            fields = {}

            # Extract Dublin Core metadata
            title_meta = book.get_metadata("DC", "title")
            if title_meta:
                fields["title"] = title_meta[0][0]

            creator_meta = book.get_metadata("DC", "creator")
            if creator_meta:
                # Join multiple creators
                creators = [meta[0] for meta in creator_meta]
                fields["author"] = ", ".join(creators)

            language_meta = book.get_metadata("DC", "language")
            if language_meta:
                fields["language"] = language_meta[0][0]

            publisher_meta = book.get_metadata("DC", "publisher")
            if publisher_meta:
                fields["publisher"] = publisher_meta[0][0]

            date_meta = book.get_metadata("DC", "date")
            if date_meta:
                fields["date"] = date_meta[0][0]

            identifier_meta = book.get_metadata("DC", "identifier")
            if identifier_meta:
                # Often contains ISBN or UUID
                fields["identifier"] = identifier_meta[0][0]

            result = {
                "container": "epub",
                "tag_format": "opf",
                "fields": fields,
            }

            return result

        except Exception:
            return None


def build_default_registry() -> ExtractorRegistry:
    """Build the default registry with all available extractors."""
    return ExtractorRegistry(
        [
            MutagenAudioExtractor(),
            MediaInfoVideoExtractor(),
            EpubExtractor(),
        ]
    )
