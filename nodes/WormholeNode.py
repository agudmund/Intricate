#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/WormholeNode.py WormholeNode class
-Collects source_path values from wired nodes and exports a Premiere .prproj for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import gzip
import uuid as _uuid
from pathlib import Path

import subprocess
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QLinearGradient, QBrush

from nodes.BaseNode import BaseNode
from data.WormholeNodeData import WormholeNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("wormhole")

# ── Visual accent ─────────────────────────────────────────────────────────────
_ACCENT          = QColor("#8b5cf6")   # Purple portal accent
_ACCENT_DIM      = QColor("#6d28d9")
_ACCENT_GLOW     = QColor(139, 92, 246, 60)
_TEXT_COLOR      = QColor("#d2d1cf")
_STATUS_OK_COLOR = QColor("#86efac")   # soft green
_STATUS_ERR_COLOR= QColor("#fca5a5")   # soft red
_IDLE_COLOR      = QColor("#a0aec0")   # muted blue-grey

# ── Blank skeleton path ───────────────────────────────────────────────────────
_SKELETON_PATH = Path(r"C:\Users\thisg\Desktop\Wormhole\The Alpaca Cooking Show.prproj")


class WormholeNode(BaseNode):
    """
    WormholeNode — Premiere Pro .prproj exporter.

    Connect ImageNode or VideoNode instances to any port. Click Export.
    The node reads source_path from all connected nodes, builds a Premiere
    project with those files in the bin, and writes it to the Adobe Documents
    folder named after the current Intricate session.

    Premiere XML structure (bin-only, no timeline):
        For each media file:
            Media (ObjectUID=uuid)              — file path + metadata
            VideoMediaSource (ObjectID=int)     — references Media via ObjectURef
            VideoClip (ObjectID=int)            — references VideoMediaSource as Source
            MasterClip (ObjectUID=uuid)         — references VideoClip via Clips list
            ClipProjectItem (ObjectUID=uuid)    — references MasterClip, shown in bin

    ObjectIDs start from NextID read from the skeleton. UUIDs are fresh for each export.
    """

    def __init__(self, data: WormholeNodeData | None = None):
        if data is None:
            data = WormholeNodeData()
        super().__init__(data)
        self._status_text     = data.last_status or ""
        self._status_ok       = True
        self._last_export_dir: Path | None = (
            Path(data.last_export_dir) if data.last_export_dir else None
        )

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton, EmojiButton
        super()._build_buttons()

        export_pix = Theme.icon(Theme.iconWormhole, fallback_color="#8b5cf6")
        export_btn = NodeButton(self, export_pix, self._export_prproj)
        export_btn.setToolTip("Export .prproj — send connected media to Premiere Pro")
        self._buttons.append(export_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTED SOURCE PATHS
    # ─────────────────────────────────────────────────────────────────────────

    def _collect_source_paths(self) -> list[str]:
        """Walk all connections, pull source_path from any connected node's data."""
        seen = set()
        paths = []
        for conn in list(self.connections):
            try:
                # We accept media from either direction of the wire
                other = conn.end_node if conn.start_node is self else conn.start_node
            except RuntimeError:
                continue
            if other is None or other is self:
                continue
            sp = getattr(getattr(other, "data", None), "source_path", None)
            if sp and sp not in seen and Path(sp).exists():
                seen.add(sp)
                paths.append(sp)
        return paths

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION NAME
    # ─────────────────────────────────────────────────────────────────────────

    def _session_info(self) -> tuple[str, Path | None]:
        """
        Return (session_name, session_root).

        Priority:
          1. settings.toml [session] last_loaded — saved session, gives both name and root
          2. main window project_selector.currentText() + _session_path() — live name even
             when the session hasn't been saved yet
          3. Fallback: ("untitled", None) → writes to Desktop/Adobe/
        """
        # 1. Saved session path
        try:
            from utils.session import project_root_from_session
            import pretty_widgets.utils.settings as _s
            last = _s.get("session", "last_loaded", "")
            if last:
                p = Path(last)
                return p.stem, project_root_from_session(p)
        except Exception:
            pass

        # 2. Live window title / project selector
        try:
            from utils.session import project_root_from_session
            scene = self.scene()
            if scene and scene.views():
                win = scene.views()[0].window()
                name = win.project_selector.currentText().strip()
                if name and name != getattr(win, '_NEW_SESSION_SENTINEL', '+ New Session'):
                    session_p = win._session_path(name)
                    root = project_root_from_session(session_p) if session_p else None
                    return name, root
        except Exception:
            pass

        return "untitled", None

    # ─────────────────────────────────────────────────────────────────────────
    # OUTPUT PATH
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _output_path(session_name: str, session_root: Path | None) -> Path:
        """
        Resolve the .prproj output path.

        Target: {session_root}/Adobe/{session_name}.prproj
        Fallback (no session): Desktop/Adobe/{session_name}.prproj
        """
        base = session_root if session_root else Path.home() / "Desktop"
        out_dir = base / "Adobe"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{session_name}.prproj"

    # ─────────────────────────────────────────────────────────────────────────
    # PRPROJ INJECTION
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_image_ext(path: Path) -> bool:
        return path.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff",
            ".psd", ".psb", ".ai", ".eps",
        }

    def _build_xml_blocks(self, paths: list[str], next_id: int) -> tuple[str, int, list[str]]:
        """
        Build XML for all media files. Returns (xml_string, updated_next_id, clip_item_uids).

        For each file we generate 5 objects:
            Media (ObjectUID)
            VideoMediaSource (ObjectID)
            VideoClip (ObjectID)
            MasterClip (ObjectUID)
            ClipProjectItem (ObjectUID)

        Media uses ObjectUID (a UUID string), other elements use ObjectID (integer).
        NextID in the project is an integer — we increment it for each new ObjectID.
        """
        blocks = []
        clip_uids: list[str] = []
        oid = next_id   # current integer ID counter

        for p in paths:
            file_path = Path(p)
            title = file_path.name
            is_image = self._is_image_ext(file_path)

            # Fresh UUIDs for UID-bearing objects
            media_uid     = str(_uuid.uuid4())
            masterclip_uid = str(_uuid.uuid4())
            clip_item_uid  = str(_uuid.uuid4())
            file_key      = str(_uuid.uuid4())
            impl_id       = str(_uuid.uuid4())
            clip_id       = str(_uuid.uuid4())

            # Integer IDs for ObjectID-bearing objects
            media_src_oid = oid;     oid += 1
            video_clip_oid= oid;     oid += 1

            # Relative path: use just filename as Premiere will search
            rel_path = f".\\{title}"

            # Media block
            media_block = (
                f'\t<Media ObjectUID="{media_uid}" '
                f'ClassID="7a5c103e-f3ac-4391-b6b4-7cc3d2f9a7ff" Version="30">\n'
                f'\t\t<RelativePath>{rel_path}</RelativePath>\n'
                f'\t\t<FilePath>{p}</FilePath>\n'
                f'\t\t<ImplementationID>{impl_id}</ImplementationID>\n'
                f'\t\t<Title>{title}</Title>\n'
                f'\t\t<FileKey>{file_key}</FileKey>\n'
            )
            if is_image:
                media_block += '\t\t<Infinite>true</Infinite>\n'
            media_block += (
                f'\t\t<ActualMediaFilePath>{p}</ActualMediaFilePath>\n'
                f'\t</Media>\n'
            )

            # VideoMediaSource block
            media_src_block = (
                f'\t<VideoMediaSource ObjectID="{media_src_oid}" '
                f'ClassID="e64ddf74-8fac-4682-8aa8-0e0ca2248949" Version="2">\n'
                f'\t\t<MediaSource Version="4">\n'
                f'\t\t\t<Content Version="10">\n'
                f'\t\t\t</Content>\n'
                f'\t\t\t<Media ObjectURef="{media_uid}"/>\n'
                f'\t\t</MediaSource>\n'
                f'\t</VideoMediaSource>\n'
            )

            # VideoClip block
            video_clip_block = (
                f'\t<VideoClip ObjectID="{video_clip_oid}" '
                f'ClassID="9308dbef-2440-4acb-9ab2-953b9a4e82ec" Version="11">\n'
                f'\t\t<Clip Version="18">\n'
                f'\t\t\t<Node Version="1">\n'
                f'\t\t\t\t<Properties Version="1">\n'
                f'\t\t\t\t</Properties>\n'
                f'\t\t\t</Node>\n'
                f'\t\t\t<Source ObjectRef="{media_src_oid}"/>\n'
                f'\t\t\t<ClipID>{clip_id}</ClipID>\n'
                f'\t\t\t<InUse>false</InUse>\n'
                f'\t\t</Clip>\n'
                f'\t</VideoClip>\n'
            )

            # MasterClip block
            masterclip_block = (
                f'\t<MasterClip ObjectUID="{masterclip_uid}" '
                f'ClassID="fb11c33a-b0a9-4465-aa94-b6d5db2628cf" Version="12">\n'
                f'\t\t<Clips Version="1">\n'
                f'\t\t\t<Clip Index="0" ObjectRef="{video_clip_oid}"/>\n'
                f'\t\t</Clips>\n'
                f'\t\t<Name>{title}</Name>\n'
                f'\t\t<MasterClipChangeVersion>1</MasterClipChangeVersion>\n'
                f'\t</MasterClip>\n'
            )

            # ClipProjectItem block
            clip_item_block = (
                f'\t<ClipProjectItem ObjectUID="{clip_item_uid}" '
                f'ClassID="cb4e0ed7-aca1-4171-8525-e3658dec06dd" Version="1">\n'
                f'\t\t<ProjectItem Version="1">\n'
                f'\t\t\t<Node Version="1">\n'
                f'\t\t\t\t<Properties Version="1">\n'
                f'\t\t\t\t</Properties>\n'
                f'\t\t\t</Node>\n'
                f'\t\t\t<Name>{title}</Name>\n'
                f'\t\t</ProjectItem>\n'
                f'\t\t<MasterClip ObjectURef="{masterclip_uid}"/>\n'
                f'\t</ClipProjectItem>\n'
            )

            clip_uids.append(clip_item_uid)
            blocks.append(media_block + media_src_block + video_clip_block
                          + masterclip_block + clip_item_block)

        return "\n".join(blocks), oid, clip_uids

    # ─────────────────────────────────────────────────────────────────────────
    # SEQUENCE XML BUILDER
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_sequence_xml(session_name: str, next_id: int) -> tuple[str, int, str, str]:
        """
        Build the 13 Premiere XML objects that form an empty default sequence.

        Objects injected (in order):
            1.  ClipLoggingInfo         (integer ObjectID)
            2.  AudioComponentChain     (integer ObjectID)
            3.  ClipChannelGroupVectorSerializer  (integer ObjectID) — "AudioClipChannelGroups"
            4.  VideoClip               (integer ObjectID) — source = VideoSequenceSource
            5.  AudioClip               (integer ObjectID) — source = AudioSequenceSource
            6.  VideoSequenceSource     (ObjectUID uuid) — refs Sequence UUID
            7.  AudioSequenceSource     (ObjectUID uuid) — refs Sequence UUID
            8.  MasterClip             (ObjectUID uuid) — refs LoggingInfo, AudioComp,
                                                          VideoClip, AudioClip, ChannelGroups
            9.  ClipProjectItem        (ObjectUID uuid) — refs MasterClip, shown in bin
            10. VideoClipTrack         (ObjectUID uuid) — empty, Index=0
            11. AudioClipTrack         (ObjectUID uuid) — empty, Index=0
            12. VideoTrackGroup        (integer ObjectID)
            13. AudioTrackGroup        (integer ObjectID)
            14. DataTrackGroup         (integer ObjectID)
            15. Sequence               (ObjectUID uuid) — refs all three track groups

        Returns (xml_string, final_next_id, seq_uid, clip_item_uid).
        The caller must update <NextID> by replacing the old value with final_next_id.
        """
        # ── Integer ObjectIDs ─────────────────────────────────────────────────
        oid = next_id
        logging_oid     = oid; oid += 1
        audio_chain_oid = oid; oid += 1
        chan_groups_oid  = oid; oid += 1
        video_clip_oid   = oid; oid += 1
        audio_clip_oid   = oid; oid += 1
        vtg_oid          = oid; oid += 1   # VideoTrackGroup
        atg_oid          = oid; oid += 1   # AudioTrackGroup
        dtg_oid          = oid; oid += 1   # DataTrackGroup

        # ── UUID-bearing objects ───────────────────────────────────────────────
        seq_uid          = str(_uuid.uuid4())
        vid_seq_src_uid  = str(_uuid.uuid4())
        aud_seq_src_uid  = str(_uuid.uuid4())
        masterclip_uid   = str(_uuid.uuid4())
        clip_item_uid    = str(_uuid.uuid4())
        vid_track_uid    = str(_uuid.uuid4())
        aud_track_uid    = str(_uuid.uuid4())

        # ── safe name for XML text ─────────────────────────────────────────────
        safe_name = session_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        parts: list[str] = []

        # 1. ClipLoggingInfo
        parts.append(
            f'\t<ClipLoggingInfo ObjectID="{logging_oid}" '
            f'ClassID="77ab7fdd-dcdf-465d-9906-7a330ca1e738" Version="9">\n'
            f'\t\t<MediaFrameRate>9223372036854775807</MediaFrameRate>\n'
            f'\t</ClipLoggingInfo>'
        )

        # 2. AudioComponentChain
        parts.append(
            f'\t<AudioComponentChain ObjectID="{audio_chain_oid}" '
            f'ClassID="3cb131d1-d3c0-47ae-a19a-bdf75ea11674" Version="3">\n'
            f'\t\t<DefaultVol>true</DefaultVol>\n'
            f'\t\t<DefaultVolumeComponentID>1</DefaultVolumeComponentID>\n'
            f'\t\t<DefaultChannelVolumeComponentID>2</DefaultChannelVolumeComponentID>\n'
            f'\t\t<ComponentChain Version="3">\n'
            f'\t\t</ComponentChain>\n'
            f'\t\t<AudioChannelLayout>[{{"channellabel":100}},{{"channellabel":101}}]</AudioChannelLayout>\n'
            f'\t\t<ChannelType>1</ChannelType>\n'
            f'\t\t<FrameRate>5760000</FrameRate>\n'
            f'\t\t<AutomationMode>1</AutomationMode>\n'
            f'\t</AudioComponentChain>'
        )

        # 3. ClipChannelGroupVectorSerializer (referenced as AudioClipChannelGroups)
        parts.append(
            f'\t<ClipChannelGroupVectorSerializer ObjectID="{chan_groups_oid}" '
            f'ClassID="a3127a8c-95d4-456e-a7f5-171b3f922426" Version="1">\n'
            f'\t\t<ClipChannelVectors Version="1">\n'
            f'\t\t</ClipChannelVectors>\n'
            f'\t</ClipChannelGroupVectorSerializer>'
        )

        # 4. VideoClip — source = VideoSequenceSource (by ObjectUID)
        vid_clip_id = str(_uuid.uuid4())
        parts.append(
            f'\t<VideoClip ObjectID="{video_clip_oid}" '
            f'ClassID="9308dbef-2440-4acb-9ab2-953b9a4e82ec" Version="11">\n'
            f'\t\t<Clip Version="18">\n'
            f'\t\t\t<Node Version="1">\n'
            f'\t\t\t\t<Properties Version="1">\n'
            f'\t\t\t\t</Properties>\n'
            f'\t\t\t</Node>\n'
            f'\t\t\t<Source ObjectURef="{vid_seq_src_uid}"/>\n'
            f'\t\t\t<ClipID>{vid_clip_id}</ClipID>\n'
            f'\t\t\t<InUse>false</InUse>\n'
            f'\t\t</Clip>\n'
            f'\t</VideoClip>'
        )

        # 5. AudioClip — source = AudioSequenceSource (by ObjectUID)
        aud_clip_id = str(_uuid.uuid4())
        parts.append(
            f'\t<AudioClip ObjectID="{audio_clip_oid}" '
            f'ClassID="b8830d03-de02-41ee-84ec-fe566dc70cd9" Version="8">\n'
            f'\t\t<Clip Version="18">\n'
            f'\t\t\t<Node Version="1">\n'
            f'\t\t\t\t<Properties Version="1">\n'
            f'\t\t\t\t</Properties>\n'
            f'\t\t\t</Node>\n'
            f'\t\t\t<Source ObjectURef="{aud_seq_src_uid}"/>\n'
            f'\t\t\t<ClipID>{aud_clip_id}</ClipID>\n'
            f'\t\t\t<InUse>false</InUse>\n'
            f'\t\t</Clip>\n'
            f'\t</AudioClip>'
        )

        # 6. VideoSequenceSource
        parts.append(
            f'\t<VideoSequenceSource ObjectUID="{vid_seq_src_uid}" '
            f'ClassID="4752dfa9-7a7e-4a3b-a25b-cafde1a8d036" Version="3">\n'
            f'\t\t<SequenceSource Version="4">\n'
            f'\t\t\t<Content Version="10">\n'
            f'\t\t\t</Content>\n'
            f'\t\t\t<Sequence ObjectURef="{seq_uid}"/>\n'
            f'\t\t</SequenceSource>\n'
            f'\t</VideoSequenceSource>'
        )

        # 7. AudioSequenceSource
        parts.append(
            f'\t<AudioSequenceSource ObjectUID="{aud_seq_src_uid}" '
            f'ClassID="e8d4cc83-38cb-491f-9d94-e5f7e3b205ee" Version="7">\n'
            f'\t\t<SequenceSource Version="4">\n'
            f'\t\t\t<Content Version="10">\n'
            f'\t\t\t</Content>\n'
            f'\t\t\t<Sequence ObjectURef="{seq_uid}"/>\n'
            f'\t\t</SequenceSource>\n'
            f'\t</AudioSequenceSource>'
        )

        # 8. MasterClip for sequence
        parts.append(
            f'\t<MasterClip ObjectUID="{masterclip_uid}" '
            f'ClassID="fb11c33a-b0a9-4465-aa94-b6d5db2628cf" Version="12">\n'
            f'\t\t<LoggingInfo ObjectRef="{logging_oid}"/>\n'
            f'\t\t<AudioComponentChains Version="1">\n'
            f'\t\t\t<AudioComponentChain Index="0" ObjectRef="{audio_chain_oid}"/>\n'
            f'\t\t</AudioComponentChains>\n'
            f'\t\t<Clips Version="1">\n'
            f'\t\t\t<Clip Index="0" ObjectRef="{video_clip_oid}"/>\n'
            f'\t\t\t<Clip Index="1" ObjectRef="{audio_clip_oid}"/>\n'
            f'\t\t</Clips>\n'
            f'\t\t<AudioClipChannelGroups ObjectRef="{chan_groups_oid}"/>\n'
            f'\t\t<Name>{safe_name}</Name>\n'
            f'\t\t<MasterClipChangeVersion>1</MasterClipChangeVersion>\n'
            f'\t</MasterClip>'
        )

        # 9. ClipProjectItem — references MasterClip, appears in bin
        parts.append(
            f'\t<ClipProjectItem ObjectUID="{clip_item_uid}" '
            f'ClassID="cb4e0ed7-aca1-4171-8525-e3658dec06dd" Version="1">\n'
            f'\t\t<ProjectItem Version="1">\n'
            f'\t\t\t<Node Version="1">\n'
            f'\t\t\t\t<Properties Version="1">\n'
            f'\t\t\t\t</Properties>\n'
            f'\t\t\t</Node>\n'
            f'\t\t\t<Name>{safe_name}</Name>\n'
            f'\t\t</ProjectItem>\n'
            f'\t\t<MasterClip ObjectURef="{masterclip_uid}"/>\n'
            f'\t</ClipProjectItem>'
        )

        # 10. VideoClipTrack — empty, Index=0
        parts.append(
            f'\t<VideoClipTrack ObjectUID="{vid_track_uid}" '
            f'ClassID="f68dcd81-8805-11d5-af2d-9bfa89d4ddd4" Version="1">\n'
            f'\t\t<ClipTrack Version="2">\n'
            f'\t\t\t<Track Version="3">\n'
            f'\t\t\t\t<Node Version="1">\n'
            f'\t\t\t\t\t<Properties Version="1">\n'
            f'\t\t\t\t\t\t<TL.SQTrackShy>0</TL.SQTrackShy>\n'
            f'\t\t\t\t\t\t<MZ.TrackTargeted>1</MZ.TrackTargeted>\n'
            f'\t\t\t\t\t\t<MZ.SourceTrackState>0</MZ.SourceTrackState>\n'
            f'\t\t\t\t\t\t<MZ.SourceTrackNumber>0</MZ.SourceTrackNumber>\n'
            f'\t\t\t\t\t\t<TL.SQTrackExpanded>0</TL.SQTrackExpanded>\n'
            f'\t\t\t\t\t\t<TL.SQTrackExpandedHeight>17</TL.SQTrackExpandedHeight>\n'
            f'\t\t\t\t\t</Properties>\n'
            f'\t\t\t\t</Node>\n'
            f'\t\t\t\t<IsLocked>false</IsLocked>\n'
            f'\t\t\t\t<MediaType>228cda18-3625-4d2d-951e-348879e4ed93</MediaType>\n'
            f'\t\t\t\t<Index>0</Index>\n'
            f'\t\t\t\t<IsMuted>false</IsMuted>\n'
            f'\t\t\t\t<IsSyncLocked>true</IsSyncLocked>\n'
            f'\t\t\t\t<ID>1</ID>\n'
            f'\t\t\t</Track>\n'
            f'\t\t\t<ClipItems Version="3">\n'
            f'\t\t\t\t<TrackItems Version="1"/>\n'
            f'\t\t\t\t<MediaType>228cda18-3625-4d2d-951e-348879e4ed93</MediaType>\n'
            f'\t\t\t\t<Index>0</Index>\n'
            f'\t\t\t</ClipItems>\n'
            f'\t\t\t<TransitionItems Version="3">\n'
            f'\t\t\t\t<MediaType>228cda18-3625-4d2d-951e-348879e4ed93</MediaType>\n'
            f'\t\t\t\t<Index>0</Index>\n'
            f'\t\t\t</TransitionItems>\n'
            f'\t\t</ClipTrack>\n'
            f'\t</VideoClipTrack>'
        )

        # 11. AudioClipTrack — empty, Index=0
        aud_track_audio_id = str(_uuid.uuid4())
        parts.append(
            f'\t<AudioClipTrack ObjectUID="{aud_track_uid}" '
            f'ClassID="097f6203-99ae-11d5-84f2-8cf14bde7040" Version="6">\n'
            f'\t\t<ClipTrack Version="2">\n'
            f'\t\t\t<Track Version="3">\n'
            f'\t\t\t\t<Node Version="1">\n'
            f'\t\t\t\t\t<Properties Version="1">\n'
            f'\t\t\t\t\t\t<TL.SQTrackShy>0</TL.SQTrackShy>\n'
            f'\t\t\t\t\t\t<TL.SQTrackAudioKeyframeStyle>0</TL.SQTrackAudioKeyframeStyle>\n'
            f'\t\t\t\t\t\t<MZ.TrackTargeted>1</MZ.TrackTargeted>\n'
            f'\t\t\t\t\t\t<MZ.SourceTrackState>1</MZ.SourceTrackState>\n'
            f'\t\t\t\t\t\t<MZ.SourceTrackNumber>0</MZ.SourceTrackNumber>\n'
            f'\t\t\t\t\t\t<CM.KeyframeMode>true</CM.KeyframeMode>\n'
            f'\t\t\t\t\t\t<TL.SQTrackExpanded>0</TL.SQTrackExpanded>\n'
            f'\t\t\t\t\t\t<TL.SQTrackExpandedHeight>41</TL.SQTrackExpandedHeight>\n'
            f'\t\t\t\t\t</Properties>\n'
            f'\t\t\t\t</Node>\n'
            f'\t\t\t\t<IsLocked>false</IsLocked>\n'
            f'\t\t\t\t<MediaType>80b8e3d5-6dca-4195-aefb-cb5f407ab009</MediaType>\n'
            f'\t\t\t\t<Index>0</Index>\n'
            f'\t\t\t\t<IsMuted>false</IsMuted>\n'
            f'\t\t\t\t<IsSyncLocked>true</IsSyncLocked>\n'
            f'\t\t\t\t<ID>2</ID>\n'
            f'\t\t\t</Track>\n'
            f'\t\t\t<ClipItems Version="3">\n'
            f'\t\t\t\t<TrackItems Version="1"/>\n'
            f'\t\t\t\t<MediaType>80b8e3d5-6dca-4195-aefb-cb5f407ab009</MediaType>\n'
            f'\t\t\t\t<Index>0</Index>\n'
            f'\t\t\t</ClipItems>\n'
            f'\t\t\t<TransitionItems Version="3">\n'
            f'\t\t\t\t<MediaType>80b8e3d5-6dca-4195-aefb-cb5f407ab009</MediaType>\n'
            f'\t\t\t\t<Index>0</Index>\n'
            f'\t\t\t</TransitionItems>\n'
            f'\t\t</ClipTrack>\n'
            f'\t\t<AudioTrack Version="11">\n'
            f'\t\t\t<ChannelType>1</ChannelType>\n'
            f'\t\t\t<FrameRate>5760000</FrameRate>\n'
            f'\t\t\t<AutomationMode>1</AutomationMode>\n'
            f'\t\t\t<SubType>1</SubType>\n'
            f'\t\t\t<Assign>1</Assign>\n'
            f'\t\t\t<NextPannerID>4294967279</NextPannerID>\n'
            f'\t\t\t<Solo>0</Solo>\n'
            f'\t\t\t<MutedBySolo>0</MutedBySolo>\n'
            f'\t\t\t<ID>{aud_track_audio_id}</ID>\n'
            f'\t\t</AudioTrack>\n'
            f'\t\t<RecordChannel>0</RecordChannel>\n'
            f'\t</AudioClipTrack>'
        )

        # 12. VideoTrackGroup — one video track, 1920×1080 @ 24fps
        parts.append(
            f'\t<VideoTrackGroup ObjectID="{vtg_oid}" '
            f'ClassID="9e9abf7a-0918-49c2-91ae-991b5dde77bb" Version="13">\n'
            f'\t\t<TrackGroup Version="1">\n'
            f'\t\t\t<Tracks Version="1">\n'
            f'\t\t\t\t<Track Index="0" ObjectURef="{vid_track_uid}"/>\n'
            f'\t\t\t</Tracks>\n'
            f'\t\t\t<FrameRate>10584000000</FrameRate>\n'
            f'\t\t\t<NextTrackID>2</NextTrackID>\n'
            f'\t\t</TrackGroup>\n'
            f'\t\t<FrameRect>0,0,1920,1080</FrameRect>\n'
            f'\t</VideoTrackGroup>'
        )

        # 13. AudioTrackGroup — one audio track
        atg_id = str(_uuid.uuid4())
        parts.append(
            f'\t<AudioTrackGroup ObjectID="{atg_oid}" '
            f'ClassID="9b9238b9-53a8-4cc3-b03f-b36246d052e6" Version="6">\n'
            f'\t\t<TrackGroup Version="1">\n'
            f'\t\t\t<Tracks Version="1">\n'
            f'\t\t\t\t<Track Index="0" ObjectURef="{aud_track_uid}"/>\n'
            f'\t\t\t</Tracks>\n'
            f'\t\t\t<FrameRate>5760000</FrameRate>\n'
            f'\t\t\t<NextTrackID>2</NextTrackID>\n'
            f'\t\t</TrackGroup>\n'
            f'\t\t<AutomationSafeFlags>0</AutomationSafeFlags>\n'
            f'\t\t<NumAdaptiveChannels>2</NumAdaptiveChannels>\n'
            f'\t\t<ID>{atg_id}</ID>\n'
            f'\t</AudioTrackGroup>'
        )

        # 14. DataTrackGroup — empty
        parts.append(
            f'\t<DataTrackGroup ObjectID="{dtg_oid}" '
            f'ClassID="b714b71d-6838-48dd-9b77-db19088ced7e" Version="1">\n'
            f'\t\t<TrackGroup Version="1">\n'
            f'\t\t\t<FrameRate>10584000000</FrameRate>\n'
            f'\t\t\t<NextTrackID>1</NextTrackID>\n'
            f'\t\t</TrackGroup>\n'
            f'\t</DataTrackGroup>'
        )

        # 15. Sequence — ties everything together
        parts.append(
            f'\t<Sequence ObjectUID="{seq_uid}" '
            f'ClassID="6a15d903-8739-11d5-af2d-9b7855ad8974" Version="11">\n'
            f'\t\t<Node Version="1">\n'
            f'\t\t\t<Properties Version="1">\n'
            f'\t\t\t\t<MZ.Sequence.VideoTimeDisplayFormat>100</MZ.Sequence.VideoTimeDisplayFormat>\n'
            f'\t\t\t\t<MZ.Sequence.EditingModeGUID>9678af98-a7b7-4bdb-b477-7ac9c8df4a4e</MZ.Sequence.EditingModeGUID>\n'
            f'\t\t\t\t<MZ.Sequence.PreviewUseMaxBitDepth>false</MZ.Sequence.PreviewUseMaxBitDepth>\n'
            f'\t\t\t\t<MZ.Sequence.PreviewUseMaxRenderQuality>false</MZ.Sequence.PreviewUseMaxRenderQuality>\n'
            f'\t\t\t\t<MZ.Sequence.AudioTimeDisplayFormat>200</MZ.Sequence.AudioTimeDisplayFormat>\n'
            f'\t\t\t\t<MZ.Sequence.PreviewFrameSizeWidth>1920</MZ.Sequence.PreviewFrameSizeWidth>\n'
            f'\t\t\t\t<MZ.Sequence.PreviewFrameSizeHeight>1080</MZ.Sequence.PreviewFrameSizeHeight>\n'
            f'\t\t\t\t<MZ.InPoint>-101606400000000000</MZ.InPoint>\n'
            f'\t\t\t\t<MZ.OutPoint>0</MZ.OutPoint>\n'
            f'\t\t\t</Properties>\n'
            f'\t\t</Node>\n'
            f'\t\t<PersistentGroupContainer Version="1">\n'
            f'\t\t\t<LinkContainer Version="1">\n'
            f'\t\t\t</LinkContainer>\n'
            f'\t\t</PersistentGroupContainer>\n'
            f'\t\t<TrackGroups Version="1">\n'
            f'\t\t\t<TrackGroup Version="1" Index="0">\n'
            f'\t\t\t\t<First>228cda18-3625-4d2d-951e-348879e4ed93</First>\n'
            f'\t\t\t\t<Second ObjectRef="{vtg_oid}"/>\n'
            f'\t\t\t</TrackGroup>\n'
            f'\t\t\t<TrackGroup Version="1" Index="1">\n'
            f'\t\t\t\t<First>80b8e3d5-6dca-4195-aefb-cb5f407ab009</First>\n'
            f'\t\t\t\t<Second ObjectRef="{atg_oid}"/>\n'
            f'\t\t\t</TrackGroup>\n'
            f'\t\t\t<TrackGroup Version="1" Index="2">\n'
            f'\t\t\t\t<First>d8143ffe-eec4-4d2a-a909-d5f7bf094dc5</First>\n'
            f'\t\t\t\t<Second ObjectRef="{dtg_oid}"/>\n'
            f'\t\t\t</TrackGroup>\n'
            f'\t\t</TrackGroups>\n'
            f'\t\t<Name>{safe_name}</Name>\n'
            f'\t\t<PreviewFormatIdentifier>f207e76a-91bb-b1d1-023f-5c54000000ea</PreviewFormatIdentifier>\n'
            f'\t</Sequence>'
        )

        return "\n".join(parts), oid, seq_uid, clip_item_uid

    def _inject_into_skeleton(self, paths: list[str], session_name: str = "untitled") -> bytes:
        """
        Load the blank skeleton, inject media objects + default empty sequence,
        update NextID, recompress.  Returns the raw gzip bytes ready to write.
        """
        if not _SKELETON_PATH.exists():
            raise FileNotFoundError(f"Skeleton not found: {_SKELETON_PATH}")

        with gzip.open(str(_SKELETON_PATH), "rb") as f:
            xml_bytes = f.read()

        xml = xml_bytes.decode("utf-8")

        # Read NextID
        import re
        m = re.search(r"<NextID>(\d+)</NextID>", xml)
        if not m:
            raise ValueError("Could not find <NextID> in skeleton")
        next_id = int(m.group(1))

        # Build the new XML blocks — media first, then sequence
        new_blocks, updated_id, media_item_uids = self._build_xml_blocks(paths, next_id)
        seq_xml, updated_id, seq_uid, seq_item_uid = self._build_sequence_xml(session_name, updated_id)

        # Update NextID
        xml = xml.replace(
            f"<NextID>{next_id}</NextID>",
            f"<NextID>{updated_id}</NextID>"
        )

        # Populate the RootProjectItem bin — register all ClipProjectItem UUIDs
        all_item_uids = media_item_uids + [seq_item_uid]
        items_xml = "\n".join(
            f'\t\t\t<Item Index="{i}" ObjectURef="{uid}"/>'
            for i, uid in enumerate(all_item_uids)
        )
        xml = xml.replace(
            '<ProjectItemContainer Version="1">\n\t\t</ProjectItemContainer>',
            f'<ProjectItemContainer Version="1">\n'
            f'\t\t\t<Items Version="1">\n'
            f'{items_xml}\n'
            f'\t\t\t</Items>\n'
            f'\t\t</ProjectItemContainer>'
        )

        # Inject sequence UUID into open-sequence list before TL.PJSnappingState
        open_seq_tag = "<TL.PJSnappingState>"
        if open_seq_tag in xml:
            xml = xml.replace(
                open_seq_tag,
                f"<MZ.PrefixKey.OpenSequenceGuidList.1>{seq_uid}</MZ.PrefixKey.OpenSequenceGuidList.1>\n"
                f"\t\t\t\t\t{open_seq_tag}"
            )

        # Inject all blocks before </PremiereData>
        closing_tag = "</PremiereData>"
        if closing_tag not in xml:
            raise ValueError("Could not find </PremiereData> in skeleton")

        combined = new_blocks + "\n" + seq_xml + "\n"
        xml = xml.replace(closing_tag, combined + closing_tag)

        # Recompress
        out = gzip.compress(xml.encode("utf-8"), compresslevel=6)
        return out

    # ─────────────────────────────────────────────────────────────────────────
    # EXPORT ACTION
    # ─────────────────────────────────────────────────────────────────────────

    def _export_prproj(self) -> None:
        """Export button handler — collect paths, inject into skeleton, write file."""
        paths = self._collect_source_paths()

        if not paths:
            self._set_status("no media connected", ok=False)
            return

        session_name, session_root = self._session_info()
        out_path = self._output_path(session_name, session_root)

        try:
            prproj_bytes = self._inject_into_skeleton(paths, session_name)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(prproj_bytes)
            n = len(paths)
            status = f"Written \u2192 ...{out_path.parent.name}/{out_path.name}  ({n} file{'s' if n != 1 else ''})"
            self._last_export_dir     = out_path.parent
            self.data.last_export_dir = str(out_path.parent)
            self._set_status(status, ok=True)
            self._show_window_status(status, out_path.parent)
            logger.info(f"[WORMHOLE] exported {n} files to {out_path}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}", ok=False)
            logger.error(f"[WORMHOLE] export failed: {exc}")

    def _set_status(self, text: str, ok: bool = True) -> None:
        self._status_text     = text
        self._status_ok       = ok
        self.data.last_status = text
        self.update()

    def _show_window_status(self, message: str, folder: Path) -> None:
        """Push export feedback to the main window bottom bar with a folder-open click."""
        try:
            scene = self.scene()
            if scene and scene.views():
                win = scene.views()[0].window()
                win.show_info(
                    message,
                    on_click=lambda: subprocess.Popen(["explorer", str(folder)])
                )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        """
        Draw:
          1. Subtle purple gradient stripe at the top
          2. List of connected filenames (or placeholder text)
          3. Status text at the bottom
        """
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        r = self.rect()
        top = self._content_top()
        pad = 10.0

        # ── Purple top accent bar ─────────────────────────────────────────────
        accent_h = 3.0
        accent_rect = QRectF(r.left() + 4, r.top() + top - 4, r.width() - 8, accent_h)
        grad = QLinearGradient(accent_rect.left(), 0, accent_rect.right(), 0)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.5, _ACCENT)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(accent_rect, 1.5, 1.5)

        # ── Filenames from connected nodes ────────────────────────────────────
        paths = self._collect_source_paths()
        content_top = r.top() + top + 6
        content_rect = QRectF(r.left() + pad, content_top,
                              r.width() - pad * 2, r.height() - top - 40)

        font = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeLabel - 1))
        painter.setFont(font)

        if not paths:
            painter.setPen(_IDLE_COLOR)
            painter.drawText(content_rect, Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
                             "Connect ImageNodes or VideoNodes,\nthen click Export.")
        else:
            painter.setPen(_TEXT_COLOR)
            lines = [Path(p).name for p in paths]
            display = "\n".join(lines[:12])
            if len(lines) > 12:
                display += f"\n\u2026 +{len(lines) - 12} more"
            painter.drawText(content_rect, Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, display)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        self.data.last_status = self._status_text
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'WormholeNode':
        return WormholeNode(WormholeNodeData.from_dict(data))
