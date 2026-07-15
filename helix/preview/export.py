"""Export preview frames to MP4/GIF backends."""


class PreviewExporter:
    def export(self, frames, output_path, format="mp4"):
        """Placeholder export API.

        Encoder integration will be added once renderer backend is selected.
        """
        return {
            "output": str(output_path),
            "format": format,
            "frames": len(frames),
        }
