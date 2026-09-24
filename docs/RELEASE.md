# Release preparation

The repository is https://github.com/Lechtob/ha-neoom. The first release is being
prepared; PyPI publication must succeed before installing through HACS.

Before a public release:

1. Configure the PyPI pending publisher for `neoom-connect`: GitHub owner
   `Lechtob`, repository `ha-neoom`, workflow `publish.yml`, environment `pypi`.
2. Run the Linux CI jobs and HACS/Hassfest validation.
3. Run the Publish Python package workflow, verify its import from a clean environment,
   then release the integration requiring that exact version.
4. Install through a HACS custom repository and verify a normal HA restart and
   Energy Dashboard statistics over time.

Local, cloud-only and hybrid live smoke tests have passed in an isolated
Home Assistant core; see [VALIDATION.md](VALIDATION.md). A simulated local
failure exercised real cloud fallback and subsequent real local recovery.

Build locally with Python 3.14:

```console
python -m pip install -e ".[test,build]" -r requirements_test.txt
python -m pytest
python -m build
python tools/build_hacs_zip.py
```

`dist/neoom.zip` contains only `custom_components/neoom`. It intentionally does
not embed the Python package. Before PyPI publication, testing on a standalone
HA virtual environment requires installing the generated wheel into that same
environment first. The isolated live test in this repository already uses the
locally installed development package. No production HA files are changed.

Credentials and local diagnostic reports are ignored by Git and excluded from
the component archive. Package contents must be inspected before upload.
