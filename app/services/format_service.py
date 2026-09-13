"""Service for normalizing raw yt-dlp formats into application-level formats."""


class FormatService:
    """Transform raw yt-dlp formats into a clean, normalized structure."""

    # Preferred video containers in order of preference
    VIDEO_EXT_PREFERENCE = ['mp4', 'webm', 'mkv']
    AUDIO_EXT_PREFERENCE = ['m4a', 'webm', 'opus']

    def normalize(self, raw_formats):
        """Convert raw yt-dlp format list into normalized video/audio lists.

        Returns a dict: {'video': [...], 'audio': [...]}
        """
        video_formats = []
        audio_formats = []

        for fmt in raw_formats or []:
            vcodec = fmt.get('vcodec') or 'none'
            acodec = fmt.get('acodec') or 'none'
            height = fmt.get('height')
            abr = fmt.get('abr')

            is_video = vcodec != 'none' and height
            is_audio = acodec != 'none'

            if is_video and not is_audio:
                video_formats.append(self._normalize_video_format(fmt))
            elif is_audio and not is_video:
                audio_formats.append(self._normalize_audio_format(fmt))
            elif is_video and is_audio:
                # Combined format (video + audio in one stream). Expose as video.
                video_formats.append(self._normalize_video_format(fmt, combined=True))

        video_formats = self._dedupe_video(video_formats)
        audio_formats = self._dedupe_audio(audio_formats)

        video_formats.sort(key=lambda f: (f.get('height') or 0, f.get('fps') or 0), reverse=True)
        audio_formats.sort(key=lambda f: f.get('bitrate') or 0, reverse=True)

        return {'video': video_formats, 'audio': audio_formats}

    def _normalize_video_format(self, fmt, combined=False):
        height = fmt.get('height') or 0
        return {
            'format_id': fmt.get('format_id'),
            'quality': f"{height}p" if height else (fmt.get('format_note') or 'unknown'),
            'height': height,
            'width': fmt.get('width'),
            'fps': fmt.get('fps'),
            'ext': fmt.get('ext'),
            'vcodec': fmt.get('vcodec'),
            'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
            'combined': combined,
        }

    def _normalize_audio_format(self, fmt):
        abr = fmt.get('abr') or fmt.get('tbr') or 0
        return {
            'format_id': fmt.get('format_id'),
            'quality': f"{int(abr)}kbps" if abr else 'unknown',
            'bitrate': int(abr) if abr else None,
            'ext': fmt.get('ext'),
            'acodec': fmt.get('acodec'),
            'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
        }

    def _dedupe_video(self, formats):
        """Keep the best format per (height, fps) combination, preferring mp4."""
        best = {}
        for fmt in formats:
            key = (fmt.get('height'), fmt.get('fps'))
            if key not in best:
                best[key] = fmt
            else:
                current = best[key]
                if self._ext_rank(fmt.get('ext'), self.VIDEO_EXT_PREFERENCE) < \
                   self._ext_rank(current.get('ext'), self.VIDEO_EXT_PREFERENCE):
                    best[key] = fmt
        return list(best.values())

    def _dedupe_audio(self, formats):
        """Keep the best format per bitrate, preferring m4a."""
        best = {}
        for fmt in formats:
            key = fmt.get('bitrate')
            if key not in best:
                best[key] = fmt
            else:
                current = best[key]
                if self._ext_rank(fmt.get('ext'), self.AUDIO_EXT_PREFERENCE) < \
                   self._ext_rank(current.get('ext'), self.AUDIO_EXT_PREFERENCE):
                    best[key] = fmt
        return list(best.values())

    @staticmethod
    def _ext_rank(ext, preference):
        try:
            return preference.index(ext)
        except (ValueError, TypeError):
            return len(preference)
