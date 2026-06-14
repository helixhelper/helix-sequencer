from __future__ import annotations

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from helix_client import HelixClient, HelixJobRequest


PROFILES = ["master", "v27.3", "v8.1", "beta", "drummer"]
STYLES = ["vendor_like", "beat_heavy", "lyrics_heavy", "drummer_focused", "gentle_preview"]
LAYOUTS = ["aaatest", "helixia", "gp_legacy", "snowman_band"]


class HelixMobileRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), padding=dp(14), **kwargs)
        self.client = HelixClient()
        self.last_job_id = None

        self.add_widget(Label(text="Helix Mobile", font_size="28sp", size_hint_y=None, height=dp(42)))
        self.add_widget(Label(text="Audio in. Lights out.", size_hint_y=None, height=dp(28)))

        self.audio_path = TextInput(
            hint_text="Audio file path or Android content reference",
            multiline=False,
            size_hint_y=None,
            height=dp(48),
        )
        self.add_widget(self.audio_path)

        self.profile = Spinner(text="master", values=PROFILES, size_hint_y=None, height=dp(48))
        self.add_widget(self.profile)

        self.style = Spinner(text="vendor_like", values=STYLES, size_hint_y=None, height=dp(48))
        self.add_widget(self.style)

        self.layout_name = Spinner(text="aaatest", values=LAYOUTS, size_hint_y=None, height=dp(48))
        self.add_widget(self.layout_name)

        self.submit = Button(text="Generate Sequence", size_hint_y=None, height=dp(56))
        self.submit.bind(on_press=self.on_submit)
        self.add_widget(self.submit)

        self.refresh = Button(text="Refresh Last Job", size_hint_y=None, height=dp(48))
        self.refresh.bind(on_press=self.on_refresh)
        self.add_widget(self.refresh)

        mode = "Mock mode" if self.client.is_mock else f"API: {self.client.base_url}"
        self.status = Label(text=mode, halign="left", valign="top")
        self.status.bind(size=self._sync_status_text_size)
        self.add_widget(self.status)

    def _sync_status_text_size(self, *_args):
        self.status.text_size = self.status.size

    def set_status(self, text: str) -> None:
        self.status.text = text

    def on_submit(self, *_args):
        audio = self.audio_path.text.strip()
        if not audio:
            self.set_status("Add an audio path first. File picker comes in the next slice.")
            return

        self.submit.disabled = True
        self.set_status("Submitting Helix job...")
        Clock.schedule_once(lambda _dt: self._submit_job(audio), 0)

    def _submit_job(self, audio: str) -> None:
        try:
            result = self.client.submit_job(
                HelixJobRequest(
                    audio_path=audio,
                    profile=self.profile.text,
                    style=self.style.text,
                    layout=self.layout_name.text,
                )
            )
            self.last_job_id = result.job_id
            self.set_status(self._format_result(result))
        except Exception as exc:  # pragma: no cover - visible in UI.
            self.set_status(f"Job failed: {exc}")
        finally:
            self.submit.disabled = False

    def on_refresh(self, *_args):
        if not self.last_job_id:
            self.set_status("No job submitted yet.")
            return
        try:
            result = self.client.get_status(self.last_job_id)
            self.set_status(self._format_result(result))
        except Exception as exc:  # pragma: no cover - visible in UI.
            self.set_status(f"Refresh failed: {exc}")

    @staticmethod
    def _format_result(result) -> str:
        artifacts = "\n".join(f"- {item}" for item in result.artifacts) or "- none yet"
        return (
            f"Job: {result.job_id}\n"
            f"Status: {result.status}\n"
            f"Output: {result.output_dir or 'pending'}\n"
            f"Message: {result.message}\n\n"
            f"Artifacts:\n{artifacts}"
        )


class HelixMobileApp(App):
    title = "Helix Mobile"

    def build(self):
        return HelixMobileRoot()


if __name__ == "__main__":
    HelixMobileApp().run()
