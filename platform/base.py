from typing import List, Tuple, Dict, Optional, Protocol


class PlatformHooks(Protocol):
    os_name: str
    bin_ext: str
    default_language: str

    def get_encoder_presets(self) -> Dict:
        ...

    def get_hw_encoder_map(self) -> List[Tuple[str, List[str]]]:
        ...

    def detect_pci_gpus(self) -> List[Tuple[str, str]]:
        ...

    def detect_vulkan_gpus(self) -> List[Tuple[int, str, str]]:
        ...

    def choose_gpu_settings(self, width: int, height: int) -> Dict:
        ...

    def interactive_select(self, prompt: str, options: List[str]) -> int:
        ...

    def interactive_select_video(self, options: List[str]) -> int:
        ...
