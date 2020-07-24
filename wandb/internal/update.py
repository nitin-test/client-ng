from pkg_resources import parse_version
import requests
import wandb


def check_available(current_version):
    timeout = 2  # Two seconds.
    pypi_url = "https://pypi.org/pypi/%s/json" % wandb._wandb_module
    try:
        data = requests.get(pypi_url, timeout=timeout).json()
        latest_version = data["info"]["version"]
        release_list = data["releases"].keys()
    except Exception:
        # Any issues whatsoever, just skip the latest version check.
        return

    # Return if no update is available
    pip_prerelease = False
    parsed_current_version = parse_version(current_version)
    if parse_version(latest_version) <= parsed_current_version:
        # pre-releases are not included in latest_version
        # so if we are currently running a pre-release we check more
        if not parsed_current_version.is_prerelease:
            return
        # Candidates are pre-releases with the same base_version
        release_list = map(parse_version, release_list)
        release_list = filter(lambda v: v.is_prerelease, release_list)
        release_list = filter(
            lambda v: v.base_version == parsed_current_version.base_version,
            release_list,
        )
        release_list = sorted(release_list)
        if not release_list:
            return
        parsed_latest_version = release_list[-1]
        if parsed_latest_version <= parsed_current_version:
            return
        latest_version = str(parsed_latest_version)
        pip_prerelease = True

    # A new version is available!
    wandb.termlog(
        "%s version %s is available!  To upgrade, please run:\n"
        " $ pip install %s --upgrade%s"
        % (
            wandb._wandb_module,
            latest_version,
            wandb._wandb_module,
            " --pre" if pip_prerelease else "",
        )
    )
