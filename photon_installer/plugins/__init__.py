import importlib
import pkgutil


def _execute_phase(phase_name, installer):
    """
    Iterate through all modules in the plugins package
    and execute the phase function if it exists.
    """
    # __path__ is a special variable available in __init__.py representing the package directory
    for _, module_name, ispkg in pkgutil.iter_modules(__path__):
        if ispkg or module_name.startswith('_'):
            continue  # Skip directories and private files like _my_utils.py

        full_module_name = f"{__name__}.{module_name}"
        try:
            # Import the dropped-in module (e.g., plugins.example_checks)
            mod = importlib.import_module(full_module_name)

            # Check if this specific module implements the current phase
            if hasattr(mod, phase_name):
                func = getattr(mod, phase_name)
                installer.logger.info(f"Executing {phase_name} from {full_module_name}")
                func(installer)

        except Exception as e:
            installer.logger.error(f"Error executing {phase_name} in {full_module_name}: {e}")
            raise

# Explicitly define the phase functions so the installer's
# hasattr(plugin_mod, 'pre_install') check succeeds on the plugins package.


def pre_install(installer):
    _execute_phase('pre_install', installer)


def pre_pkgs_install(installer):
    _execute_phase('pre_pkgs_install', installer)


def post_install(installer):
    _execute_phase('post_install', installer)


def final_check(installer):
    _execute_phase('final_check', installer)
