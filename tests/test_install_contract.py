from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallContractTests(unittest.TestCase):
    def test_platform_requirements_are_split_without_changing_mac_fallbacks(self):
        common = (ROOT / "requirements-common.txt").read_text()
        mac = (ROOT / "requirements-macos.txt").read_text()
        linux = (ROOT / "requirements-linux.txt").read_text()
        root_requirements = (ROOT / "requirements.txt").read_text()

        self.assertIn("PyQt6", common)
        self.assertIn("websockets", common)
        self.assertIn("Pillow", common)
        self.assertIn("sounddevice", mac)
        self.assertIn("numpy", mac)
        self.assertIn("pyobjc-framework-Cocoa", mac)
        self.assertNotIn("sounddevice", linux)
        self.assertNotIn("numpy", linux)
        self.assertIn("sys_platform == 'darwin'", root_requirements)

    def test_linux_portaudio_is_explicit(self):
        portaudio = (ROOT / "requirements-linux-portaudio.txt").read_text()
        self.assertIn("sounddevice", portaudio)
        self.assertIn("numpy", portaudio)

    def test_install_selects_system_tools_and_records_ownership(self):
        installer = (ROOT / "install.sh").read_text()
        helper = (ROOT / "scripts/kyros-system.sh").read_text()
        self.assertIn("requirements-macos.txt", installer)
        self.assertIn("requirements-linux.txt", installer)
        self.assertIn("kyros_install_system_dependencies", installer)
        self.assertIn("kyros_record_package_delta", helper)
        self.assertIn("kmod", helper)
        self.assertIn("libnotify-bin", helper)
        self.assertIn("gir1.2-atspi-2.0", helper)
        self.assertIn("KYROS_PREVIOUS_PACKAGE_MANAGER", installer)
        self.assertIn("--with-portaudio", installer)
        self.assertIn("LC_ALL=C comm -13", helper)
        self.assertIn("kyros_answer_yes", helper)
        self.assertIn("Continue? [Y/n]", helper)

    def test_uninstall_does_not_use_a_broad_autoremove(self):
        installer = (ROOT / "install.sh").read_text()
        uninstaller = (ROOT / "uninstall.sh").read_text()
        helper = (ROOT / "scripts/kyros-system.sh").read_text()
        self.assertIn("system-packages.added", helper)
        self.assertIn("kyros_remove_system_dependencies", helper)
        self.assertIn("--auto-remove", helper)  # apt cleanup is simulation-guarded
        self.assertNotIn("apt-get autoremove", helper)
        self.assertNotIn("pacman -Rs", helper)
        self.assertIn("LC_ALL=C comm -23", helper)
        self.assertIn("pacman -R --noconfirm", helper)
        self.assertIn("Continue? [y/N]", helper)
        self.assertNotIn("chmod +s", installer + uninstaller + helper)
        self.assertNotIn("chmod 777", installer + uninstaller + helper)

    def test_uinput_permission_is_scoped_to_dedicated_group(self):
        rule = (ROOT / "system/99-kyros-uinput.rules").read_text()
        service = (ROOT / "system/kyros-ydotoold.service").read_text()
        self.assertIn('KERNEL=="uinput"', rule)
        self.assertIn('GROUP="kyros-input"', rule)
        self.assertNotIn('MODE="0666"', rule)
        self.assertNotIn("ExecStart=sudo", service)
        self.assertIn("--socket-path=%t/.ydotool_socket", service)


if __name__ == "__main__":
    unittest.main()
