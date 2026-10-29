# 0023. Distributing and deploying NEXORA applications

- **Status:** Accepted
- **Date:** 29 October 2026
- **Affects:** application installation, runtime selection, configuration and deployment guidance

## Decision

The supported baseline for a deployed NEXORA application is the Python package installed at an
exact version in an application-specific virtual environment. The deployment pins a Python patch
release separately. NEXORA has no third-party runtime dependencies, so the application dependency
lock is a single exact `nexora-lang` requirement.

Use an external configuration file for deployment-specific values. Applications declare file
access with `uses read` or `uses write`; the command that starts them grants only the needed paths.
NEXORA has no direct environment-variable API. A deployment wrapper may render environment or
secret-store values into a protected config file before starting the program. Secrets must not be
committed or passed as command-line arguments.

The npm distribution remains a convenience launcher for npm users, with Node.js and Python both
required. It is not the recommended deployment artifact because it does not bundle or provision the
Python runtime. Linux containers are an optional packaging route; the reference Dockerfile pins the
Python image by multi-platform digest as well as exact patch tag.

Python 3.13.18 and NEXORA 0.14.1 are the reference pins at acceptance. Maintainers update those
pins when adopting a newer security-patched Python and a verified NEXORA release; these pins are
not a policy to remain on those patch versions indefinitely.

## Rationale

- Python is already required by the reference interpreter and the PyPI package uses the same
  entry points as the npm launcher.
- A virtual environment isolates the CLI from system Python packages on Windows, macOS and Linux.
- There are no NEXORA runtime dependencies beyond the package itself, so a transitive dependency
  lock would add maintenance without improving application reproducibility.
- External configuration can be mounted, permissioned and rotated by the deployment platform
  without changing program source. Explicit CLI grants make file access visible at launch.
- Self-contained executables for every OS and processor architecture would add a separate runtime
  packaging and release burden and are not required for the current interpreter distribution.

## Completion criteria

- A reference application includes exact Python and NEXORA version pins.
- Clean installation, check and execution commands are documented for Windows, macOS and Linux;
  a Linux container recipe is also included.
- Configuration is external to the source and passed through a narrowly scoped file grant.
- The guide states npm's Python requirement and the limits of reproducibility and platform testing.

## Revisit when

The runtime gains third-party dependencies, the supported Python matrix changes, a first-party
environment-variable/configuration API is added, or self-contained distribution becomes an
explicit project goal.
