"""Installer script (installer/pane.iss) stays consistent with the app. Static checks only:
the real install / upgrade / uninstall cycle is run by hand (see docs/HISTORY.md)."""
import re
from pathlib import Path

from core import version
from core.media_types import VIDEO_EXTENSIONS, open_dialog_filter
from tools import installer_registry

ROOT = Path(__file__).resolve().parent.parent
ISS = (ROOT / "installer" / "pane.iss").read_text(encoding="utf-8")
EXT_ISS = (ROOT / "installer" / "extensions.iss").read_text(encoding="utf-8")


def setup_value(name):
    m = re.search(rf"^{name}=(.*)$", ISS, flags=re.M)
    assert m, f"[Setup] has no {name}"
    return m.group(1).strip()


# --- file types ------------------------------------------------------------

def test_generated_extension_registry_is_up_to_date():
    """Fails when core/media_types.py changed but tools/installer_registry.py was not re-run."""
    assert EXT_ISS == installer_registry.build_lines()


def test_every_extension_is_registered_three_ways():
    for ext in VIDEO_EXTENSIONS:
        assert f'Software\\Classes\\.{ext}\\OpenWithProgids' in EXT_ISS
        assert f'ValueName: ".{ext}"; ValueData: "Pane.Video"' in EXT_ISS          # capabilities
        assert f'Applications\\Pane.exe\\SupportedTypes' in EXT_ISS


def test_open_dialog_and_installer_use_the_same_extensions():
    dialog = open_dialog_filter()
    for ext in VIDEO_EXTENSIONS:
        assert f"*.{ext}" in dialog
    registered = set(re.findall(r'OpenWithProgids"; ValueType: string; ValueName: "Pane.Video"', EXT_ISS))
    assert registered, "no OpenWithProgids entries"
    assert len(re.findall(r"OpenWithProgids", EXT_ISS)) == len(VIDEO_EXTENSIONS)


def test_installer_never_takes_over_the_default_app():
    """'Open with' + Default-apps capabilities only. Writing a default value under
    Software\\Classes\\.<ext> (or UserChoice) would hijack the user's current player."""
    text = ISS + EXT_ISS
    assert "UserChoice" not in text
    for ext in VIDEO_EXTENSIONS:
        assert not re.search(rf'Subkey: "Software\\Classes\\\.{ext}"; ValueType: string; ValueData', text)


def test_file_association_commands_quote_the_path_and_the_argument():
    commands = re.findall(r'shell\\open\\command"; ValueType: string; ValueData: (".*")', ISS)
    assert len(commands) == 2
    for c in commands:
        assert c == '"""{app}\\{#AppExe}"" ""%1"""'


# --- identity --------------------------------------------------------------

def test_app_id_is_a_fixed_guid():
    """Changing it would make an update install next to the old version instead of replacing it."""
    assert setup_value("AppId") == "{{8C6E2F5A-3B1D-4E7A-9D52-6A1F0C4B7E31}"


def test_taskbar_identity_matches_the_code():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert f'SetCurrentProcessExplicitAppUserModelID("Pane.Player")' in main
    assert '#define AppUserModelId "Pane.Player"' in ISS
    assert 'AppUserModelID: "{#AppUserModelId}"' in ISS


def test_default_version_matches_the_app_version():
    assert f'#define AppVersion "{version.APP_VERSION}"' in ISS
    assert '#define AppName "Pane"' in ISS
    assert "OutputBaseFilename={#AppName}-{#AppVersion}-setup" in ISS


# --- install behaviour -----------------------------------------------------

def test_installs_per_user_without_admin_by_default():
    assert setup_value("PrivilegesRequired") == "lowest"
    assert setup_value("PrivilegesRequiredOverridesAllowed") == "dialog"
    assert "{autopf}" in setup_value("DefaultDirName")


def test_desktop_shortcut_is_opt_in_and_file_association_is_on_by_default():
    tasks = dict(re.findall(r'^Name: "(\w+)"; Description: [^;]+; GroupDescription: [^;]+(?:; (Flags: \w+))?$', ISS, flags=re.M))
    assert tasks["desktopicon"] == "Flags: unchecked", "the desktop shortcut must be optional (off by default)"
    assert tasks["fileassoc"] == "", "file association is registered unless the user unticks it"


def test_running_app_is_closed_during_an_update():
    assert setup_value("CloseApplications") == "yes"
    assert setup_value("ChangesAssociations") == "yes"


def test_both_languages_have_every_custom_message():
    for key in ("AssocTask", "AssocGroup", "DeleteSettingsPrompt", "AssocDescription"):
        assert f"english.{key}=" in ISS and f"korean.{key}=" in ISS, key


# --- uninstall -------------------------------------------------------------

def test_uninstall_removes_exactly_the_settings_groups_the_app_writes():
    code = "\n".join(p.read_text(encoding="utf-8") for d in ("ui", "core") for p in (ROOT / d).glob("*.py"))
    used = set(re.findall(r'open_settings\("(\w+)"\)', code))
    assert used == {"AppSettings", "ControllerLayout", "SpeedSettings"}
    for group in used:
        assert f"'Software\\Pane\\{group}'" in ISS, f"uninstall would leave {group} behind"


def test_uninstall_keeps_user_data_unless_asked():
    assert "/DELETESETTINGS" in ISS
    assert "MB_DEFBUTTON2" in ISS                 # the prompt defaults to 'No'
    assert "UninstallSilent" in ISS               # a silent uninstall never deletes data on its own


# --- silent updates started by the app ----------------------------------------------------

def test_the_installer_script_relaunches_after_a_silent_update():
    """The app starts the installer with /SILENT /RELAUNCH (core/updater.py). A silent run skips the usual "launch Pane"
    entry (skipifsilent), so a second [Run] entry brings the app back, only when /RELAUNCH was given."""
    run = ISS.split("[Run]")[1].split("[")[0]
    relaunch = [line for line in run.splitlines() if "Check: WantsRelaunch" in line]
    assert len(relaunch) == 1
    assert r'{app}\{#AppExe}' in relaunch[0] and "nowait" in relaunch[0] and "runasoriginaluser" in relaunch[0]
    assert "skipifsilent" not in relaunch[0]
    code = ISS.split("[Code]")[1]
    func = re.search(r"function WantsRelaunch\(\): Boolean;.*?^end;", code, flags=re.S | re.M)
    assert func and "/RELAUNCH" in func.group(0)


def test_the_flags_the_app_passes_are_the_flags_the_installer_script_reads():
    from core.updater import installer_command
    flags = installer_command(Path("x.exe"), "user")
    assert "/RELAUNCH" in flags and "/RELAUNCH" in ISS
    assert "CloseApplications=yes" in ISS, "/CLOSEAPPLICATIONS needs the installer to close the running app"
