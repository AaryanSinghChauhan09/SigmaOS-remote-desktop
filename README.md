    # SigmaOS-remote-desktop

    VNC/RDP remote desktop sharing

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/omacom/gliff

    ## Design principles applied
    - **Defensive Programming**
- **Separation of Concerns**
- **Fail-Fast**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `share-plan, sessions, access, stop-plan`

    ```
    $ sigma-remote share-plan --port 5901 --mode view-only
x11vnc -display :0 -rfbport 5901 -forever -shared -viewonly -nopw
$ sigma-remote sessions sessions.txt
s1|:0|5901|alice|view-only|1761316800|4242
$ sigma-remote access laptop.local --protocol rdp
xfreerdp /v:laptop.local /port:3389 /cert:ignore
$ sigma-remote stop-plan --pid 4242
kill -INT 4242

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
