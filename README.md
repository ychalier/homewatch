# Homewatch

Homewatch is a lightweight self-hosted media server.

The idea is to have media files stored on a computer or a remote server, and use
a remote device (namely, a phone) to browse the library and play some files. The
main use case is for watching movies without leaving the bed or the sofa.

## Features

- Browse a local or remote media library
- Control a remote VLC player
- Sleep mode with modular hooks
- Keep a viewing history
- Keep playlists, play them in order or shuffled
- Integrate with Google Chromecast
- Linux and Windows support
- Self-hosted: no data collection, no subscription plan, total control
- Lightweight: the media library is based on the existing file system

## Getting Started

### Hardware

Homewatch relies on three *logical* components: a media server, a video player
and a control remote. You can use the same machine for all of them, or one
machine per component, as you like. Here are two basic setup ideas:

**Bedroom setup**
- A computer acts as the media server and the video player, using local video files
- A phone remotely controls the video player on the computer

**Home setup**
- A local server (e.g. a Raspberry Pi) acts as a media server, using local video files
- A computer acts as the video player, streaming medias from the local network
- A phone remotely controls the video player on the computer

Note that I tried using a Raspberry Pi 3B+ as a video player, but performances
were to low for it to be reliable.

Each machine hosting either the media server or the video player (or both)
requires an installation of Homewatch and a specific configuration. See
instructions below.

### Prerequisite

You'll need [Python 3](https://www.python.org/) and [VLC](https://www.videolan.org/vlc/).

### Installation

1. Clone this repository
    ```console
    git clone https://github.com/ychalier/homewatch
    ```
2. Install dependencies in [requirements.txt](requirements.txt)
    ```console
    pip install -r requirements.txt
    ```
3. Edit the settings in [homewatch/settings.py](homewatch/settings.py),
   everything is explained in the comments 

### Usage

Call the main script [homewatch.py](homewatch.py) with the `runserver` argument:

```console
python homewatch.py runserver
```

Open a web browser to http://127.0.0.1:8000/, and you should see your media
library.

## Home Setup Scenario

Here is an example scenario, to get an idea of how Homewatch can be used.

A Raspberry Pi has media files stored on a hard drive. Install Homewatch on it,
set `SERVER_MODE` to `library`, `LIBRARY_MODE` to `local` and `LIBRARY_ROOT` to
the hard drive path, e.g. `/mnt/usb/`. As Homewatch server is a
[WSGI](https://wsgi.readthedocs.io/en/latest/) application, it can be embedded
within an Apache server, e.g. with [mod_wsgi](https://modwsgi.readthedocs.io/).
Here is a configuration sample:

```text
WSGIScriptAlias / /path/to/homewatch/wsgi.py

Alias /static/ /path/to/homewatch/homewatch/static/
<Directory /path/to/homewatch/homewatch/static>
    Require all granted
</Directory>

Alias /media/ /mnt/usb/
<Directory /mnt/usb>
    Require all granted
</Directory>
```

Then, on a computer, install Homewatch again, set `SERVER_MODE` to `player`,
`LIBRARY_MODE` to `remote` and `LIBRARY_ROOT` to the Raspberry Pi URL, e.g.
`http://192.168.1.42/library/`. Start Homewatch with the following command:

```console
python homewatch.py --qrcode 192.168.1.69:8000
```

The `--qrcode` flag is used to print a QR code in the terminal, that can be 
scanned with the phone to get redirected to the control remote. `192.168.1.69`
is the local IP address of the laptop.

On the phone, go to http://192.168.1.69:8000 (or scan the QR code), and voilà!

## Built With

- [Jinja](https://jinja.palletsprojects.com/en/3.0.x/) - Templating engine
- [python-vlc](https://pypi.org/project/python-vlc/) - Python bindings for [libVLC](https://www.videolan.org/vlc/libvlc.html)
- [qrcode](https://pypi.org/project/qrcode/) - QR code generator
- [requests](https://pypi.org/project/requests/) - HTTP library
- [tqdm](https://pypi.org/project/tqdm/) - Progress display
- [websockets](https://pypi.org/project/websockets/) - [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API) API implementation for Python
- [werkzeug](https://pypi.org/project/Werkzeug/) - [WSGI](https://wsgi.readthedocs.io/en/latest/) web application library

## Contributing

Contributions are welcomed. Push your branch and create a pull request detailling your changes.

## Authors

Project is maintained by [Yohan Chalier](https://chalier.fr).

## License

This project is licensed under the [GNU GPLv3](LICENSE) license.

## Troubleshooting

This project is still in an early stage. Submit bug reports and feature suggestions in the [issue tracker](https://github.com/ychalier/homewatch/issues/new/choose).