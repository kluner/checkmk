#!/usr/bin/env python3
# Copyright (C) 2022 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast, Iterator, Literal, Mapping

from livestatus import (
    LocalSocketInfo,
    NetworkSocketDetails,
    NetworkSocketInfo,
    ProxyConfig,
    ProxyConfigParams,
    ProxyConfigTcp,
    SiteConfiguration,
    SiteConfigurations,
    SiteId,
    TLSInfo,
    TLSParams,
    UnixSocketDetails,
    UnixSocketInfo,
)

from cmk.utils.type_defs._misc import UserId

from cmk.gui.site_config import site_is_local
from cmk.gui.watolib.automations import do_site_login
from cmk.gui.watolib.sites import prepare_raw_site_config, SiteManagementFactory


class SiteDoesNotExistException(Exception):
    ...


class SiteAlreadyExistsException(Exception):
    ...


class SiteVersionException(Exception):
    ...


class LoginException(Exception):
    ...


@dataclass
class Socket:
    socket_type: Literal["unix", "tcp6", "tcp", "local"] | None = None
    host: str | None = None
    port: int | None = None
    encrypted: bool | None = None
    verify: bool | None = None
    path: str | None = None

    @classmethod
    def from_internal(
        cls, internal_config: str | UnixSocketInfo | NetworkSocketInfo | LocalSocketInfo
    ) -> Socket:
        if isinstance(internal_config, str):
            return cls(socket_type="local")

        if internal_config[0] == "local":
            return cls(socket_type=internal_config[0])

        if internal_config[0] == "unix":
            return cls(socket_type=internal_config[0], path=internal_config[1].get("path"))

        host, port = internal_config[1]["address"]
        encrypt, verify_dict = internal_config[1]["tls"]
        encrypted = encrypt == "encrypted"
        verify = verify_dict.get("verify")

        return cls(
            socket_type=internal_config[0], host=host, port=port, verify=verify, encrypted=encrypted
        )

    def to_external(self) -> Iterator[tuple[str, str | int | bool]]:
        for k, v in self.__dict__.items():
            if v is not None:
                yield k, v

    def to_internal(self) -> NetworkSocketInfo | UnixSocketInfo | LocalSocketInfo:
        if self.socket_type in ("tcp", "tcp6"):
            if self.host and self.port:
                tls_params: TLSParams = {}

                if self.verify is not None:
                    tls_params["verify"] = self.verify

                encrypt_status: Literal["encrypted", "plain_text"] = (
                    "encrypted" if self.encrypted else "plain_text"
                )
                tls_info: TLSInfo = (encrypt_status, tls_params)

                networksockdetails: NetworkSocketDetails = {
                    "tls": tls_info,
                    "address": (self.host, self.port),
                }
                socket_type = cast(Literal["tcp", "tcp6"], self.socket_type)
                networksockinfo: NetworkSocketInfo = (socket_type, networksockdetails)
                return networksockinfo

        if self.path:
            details: UnixSocketDetails = {"path": self.path}
            unixsocketinfo: UnixSocketInfo = ("unix", details)
            return unixsocketinfo

        localsocketinfo: LocalSocketInfo = ("local", None)
        return localsocketinfo


@dataclass
class StatusHost:
    site: SiteId | None = None
    host: str | None = None
    status_host_set: bool = False

    @classmethod
    def from_internal(cls, internal_config: tuple[SiteId, str] | None) -> StatusHost:
        if internal_config is None:
            return cls()

        return cls(site=internal_config[0], host=str(internal_config[1]), status_host_set=True)

    def to_external(self) -> Iterator[tuple[str, str | bool | None]]:
        yield "status_host_set", self.status_host_set

        if self.status_host_set:
            yield "site", self.site
            yield "host", self.host

    def to_internal(self) -> tuple[SiteId, str] | None:
        if self.site and self.host:
            return (self.site, self.host)
        return None


@dataclass
class Heartbeat:
    interval: int
    timeout: float

    def __iter__(self) -> Iterator[tuple[str, int]]:
        for k, v in self.__dict__.items():
            yield k, v


@dataclass
class ProxyParams:
    channels: int | None = None
    heartbeat: Heartbeat | None = None
    channel_timeout: float | None = None
    query_timeout: float | None = None
    connect_retry: float | None = None
    cache: bool | None = None

    @classmethod
    def from_internal(cls, internal_config: ProxyConfigParams) -> ProxyParams:
        hb = internal_config.get("heartbeat")
        return cls(
            channels=internal_config.get("channels"),
            heartbeat=Heartbeat(*hb) if hb else None,
            channel_timeout=internal_config.get("channel_timeout"),
            query_timeout=internal_config.get("query_timeout"),
            connect_retry=internal_config.get("connect_retry"),
            cache=internal_config.get("cache"),
        )

    def to_external(self) -> Iterator[tuple[str, dict[str, int] | int | bool | float]]:
        for k, v in self.__dict__.items():
            if k == "heartbeat" and self.heartbeat is not None:
                yield k, dict(self.heartbeat)
                continue

            if v is not None:
                yield k, v

    def to_internal(self) -> ProxyConfigParams:
        proxyconfigparams: ProxyConfigParams = {}
        if self.channels is not None:
            proxyconfigparams["channels"] = self.channels

        if self.heartbeat:
            proxyconfigparams["heartbeat"] = (self.heartbeat.interval, self.heartbeat.timeout)

        if self.channel_timeout is not None:
            proxyconfigparams["channel_timeout"] = self.channel_timeout

        if self.query_timeout is not None:
            proxyconfigparams["query_timeout"] = self.query_timeout

        if self.connect_retry is not None:
            proxyconfigparams["connect_retry"] = self.connect_retry

        if self.cache is not None:
            proxyconfigparams["cache"] = self.cache

        return proxyconfigparams


@dataclass
class ProxyTcp:
    port: int | None = None
    only_from: list[str] = field(default_factory=list)
    tls: bool = False

    def to_external(self) -> Iterator[tuple[str, int | list[str] | bool]]:
        if self.port:
            for k, v in self.__dict__.items():
                yield k, v

    def to_internal(self) -> ProxyConfigTcp:
        proxyconfigtcp: ProxyConfigTcp = {}
        if self.port:
            proxyconfigtcp["port"] = self.port
            proxyconfigtcp["only_from"] = self.only_from
            proxyconfigtcp["tls"] = self.tls

        return proxyconfigtcp


@dataclass
class Proxy:
    connect_directly: bool
    params: ProxyParams | None = None
    tcp: ProxyTcp | None = None
    global_settings: bool | None = None

    @classmethod
    def from_external(cls, external_config: Mapping[str, Any]) -> Proxy:
        connect_directly = external_config["connect_directly"]

        if params := external_config.get("params"):
            if heartbeat := params.get("heartbeat"):
                params["heartbeat"] = Heartbeat(**heartbeat)
            proxyparams = ProxyParams(**params)
            global_settings = False
        else:
            proxyparams = ProxyParams()
            global_settings = True

        if tcp := external_config.get("tcp"):
            tcp_val = ProxyTcp(**tcp)
        else:
            tcp_val = ProxyTcp()

        return cls(
            connect_directly=connect_directly,
            global_settings=global_settings,
            params=proxyparams,
            tcp=tcp_val,
        )

    @classmethod
    def from_internal(cls, internal_config: ProxyConfig | None) -> Proxy:
        if internal_config is None:
            return cls(connect_directly=True)

        connect_directly = "params" not in internal_config
        if proxyconfigparams := internal_config.get("params"):
            proxyparams = ProxyParams.from_internal(proxyconfigparams)
            global_settings = False
        else:
            proxyparams = ProxyParams()
            global_settings = True

        if tcp := internal_config.get("tcp"):
            tcp_val = ProxyTcp(**tcp)
        else:
            tcp_val = ProxyTcp()

        return cls(
            connect_directly=connect_directly,
            global_settings=global_settings,
            params=proxyparams,
            tcp=tcp_val,
        )

    def to_external(self) -> Iterator[tuple[str, bool | None | dict]]:
        yield "connect_directly", self.connect_directly

        if not self.connect_directly:
            yield "global_settings", self.global_settings

            if self.params:
                if paramsdict := dict(self.params.to_external()):
                    yield "params", paramsdict

            if self.tcp:
                if tcpdict := dict(self.tcp.to_external()):
                    yield "tcp", tcpdict

    def to_internal(self) -> ProxyConfig | None:
        if self.connect_directly:
            return None

        proxyconfig: ProxyConfig = {}
        if self.params:
            if paramsdict := self.params.to_internal():
                proxyconfig["params"] = paramsdict
            else:
                proxyconfig["params"] = None

        if self.tcp:
            if tcpdict := self.tcp.to_internal():
                proxyconfigtcp: ProxyConfigTcp = tcpdict
                proxyconfig["tcp"] = proxyconfigtcp

        return proxyconfig


@dataclass
class BasicSettings:
    alias: str
    site_id: str

    @classmethod
    def from_internal(cls, site_id: SiteId, internal_config: SiteConfiguration) -> BasicSettings:
        return cls(alias=internal_config["alias"], site_id=site_id)

    def to_external(self) -> Iterator[tuple[str, str]]:
        yield "alias", self.alias
        yield "site_id", self.site_id

    def to_internal(self) -> SiteConfiguration:
        configid: SiteConfiguration = {"alias": self.alias, "id": SiteId(self.site_id)}
        return configid


@dataclass
class StatusConnection:
    connection: Socket
    proxy: Proxy
    connect_timeout: int
    persistent_connection: bool
    url_prefix: str
    status_host: StatusHost
    disable_in_status_gui: bool

    @classmethod
    def from_internal(cls, internal_config: SiteConfiguration) -> StatusConnection:
        return cls(
            connection=Socket.from_internal(internal_config["socket"]),
            proxy=Proxy.from_internal(internal_config=internal_config.get("proxy")),
            connect_timeout=internal_config["timeout"],
            persistent_connection=internal_config["persist"],
            url_prefix=internal_config.get("url_prefix", ""),
            status_host=StatusHost.from_internal(
                internal_config=internal_config.get("status_host")
            ),
            disable_in_status_gui=internal_config["disabled"],
        )

    @classmethod
    def from_external(cls, external_config: Mapping[str, Any]) -> StatusConnection:
        return cls(
            connection=Socket(**external_config["connection"]),
            proxy=Proxy.from_external(external_config["proxy"]),
            connect_timeout=external_config["connect_timeout"],
            persistent_connection=external_config["persistent_connection"],
            url_prefix=external_config["url_prefix"],
            status_host=StatusHost(**external_config["status_host"]),
            disable_in_status_gui=external_config["disable_in_status_gui"],
        )

    def to_external(self) -> Iterator[tuple[str, dict | bool | int]]:
        for k, v in self.__dict__.items():
            if k == "status_host":
                yield k, dict(self.status_host.to_external())
                continue

            if k == "connection":
                yield k, dict(self.connection.to_external())
                continue

            if k == "proxy":
                yield k, dict(self.proxy.to_external())
                continue

            yield k, v

    def to_internal(self) -> SiteConfiguration:
        statusconnection: SiteConfiguration = {
            "status_host": self.status_host.to_internal(),
            "socket": self.connection.to_internal(),
            "proxy": self.proxy.to_internal(),
            "disabled": self.disable_in_status_gui,
            "timeout": self.connect_timeout,
            "persist": self.persistent_connection,
            "url_prefix": self.url_prefix,
        }
        return statusconnection


@dataclass
class UserSync:
    sync_with_ldap_connections: str
    ldap_connections: list[str] = field(default_factory=list)

    @classmethod
    def from_internal(cls, internal_config: tuple | str | None) -> UserSync:
        if isinstance(internal_config, tuple):
            return cls(sync_with_ldap_connections="ldap", ldap_connections=internal_config[1])

        if internal_config == "all":
            return cls(sync_with_ldap_connections="all")

        return cls(sync_with_ldap_connections="disabled")

    def to_external(self) -> Iterator[tuple[str, str | None | list[str]]]:
        yield "sync_with_ldap_connections", self.sync_with_ldap_connections
        if self.ldap_connections:
            yield "ldap_connections", self.ldap_connections

    def to_internal(self) -> Literal["all"] | tuple[Literal["list"], list[str]] | None:
        if self.sync_with_ldap_connections == "all":
            return "all"

        if self.sync_with_ldap_connections == "ldap":
            return ("list", self.ldap_connections)

        return None


@dataclass
class ConfigurationConnection:
    enable_replication: bool
    url_of_remote_site: str
    disable_remote_configuration: bool
    ignore_tls_errors: bool
    direct_login_to_web_gui_allowed: bool
    user_sync: UserSync
    replicate_event_console: bool
    replicate_extensions: bool

    @classmethod
    def from_internal(
        cls, site_id: SiteId, internal_config: SiteConfiguration
    ) -> ConfigurationConnection:

        return cls(
            enable_replication=bool(internal_config["replication"]),
            url_of_remote_site=internal_config["multisiteurl"],
            disable_remote_configuration=internal_config["disable_wato"],
            ignore_tls_errors=internal_config["insecure"],
            direct_login_to_web_gui_allowed=internal_config["user_login"],
            user_sync=UserSync.from_internal(
                internal_config=internal_config.get(
                    "user_sync", "all" if site_is_local(site_id) else "disabled"
                )
            ),
            replicate_event_console=internal_config["replicate_ec"],
            replicate_extensions=internal_config.get("replicate_mkps", False),
        )

    @classmethod
    def from_external(cls, external_config: dict[str, Any]) -> ConfigurationConnection:
        external_config["user_sync"] = UserSync(**external_config["user_sync"])
        return cls(**external_config)

    def to_external(self) -> Iterator[tuple[str, dict[str, str | list[str] | None] | bool | str]]:
        for k, v in self.__dict__.items():
            if k == "user_sync":
                yield k, dict(self.user_sync.to_external())
                continue

            yield k, v

    def to_internal(self) -> SiteConfiguration:
        configconnection: SiteConfiguration = {
            "replication": "slave" if self.enable_replication else None,
            "multisiteurl": self.url_of_remote_site,
            "disable_wato": self.disable_remote_configuration,
            "insecure": self.ignore_tls_errors,
            "user_login": self.direct_login_to_web_gui_allowed,
            "user_sync": self.user_sync.to_internal(),
            "replicate_ec": self.replicate_event_console,
            "replicate_mkps": self.replicate_extensions,
        }
        return configconnection


@dataclass
class SiteConfig:
    basic_settings: BasicSettings
    status_connection: StatusConnection
    configuration_connection: ConfigurationConnection
    secret: str | None = None

    @classmethod
    def from_internal(cls, site_id: SiteId, internal_config: SiteConfiguration) -> SiteConfig:
        return cls(
            basic_settings=BasicSettings.from_internal(site_id, internal_config),
            status_connection=StatusConnection.from_internal(internal_config),
            configuration_connection=ConfigurationConnection.from_internal(
                site_id, internal_config
            ),
            secret=internal_config.get("secret"),
        )

    @classmethod
    def from_external(cls, external_config: dict[str, Any]) -> SiteConfig:
        return cls(
            basic_settings=BasicSettings(**external_config["basic_settings"]),
            status_connection=StatusConnection.from_external(external_config["status_connection"]),
            configuration_connection=ConfigurationConnection.from_external(
                external_config["configuration_connection"]
            ),
            secret=external_config.get("secret"),
        )

    def to_external(self) -> Iterator[tuple[str, dict | None | str]]:
        yield "basic_settings", dict(self.basic_settings.to_external())
        yield "status_connection", dict(self.status_connection.to_external())
        yield "configuration_connection", dict(self.configuration_connection.to_external())
        if self.secret:
            yield "secret", self.secret

    def to_internal(self) -> SiteConfiguration:
        internal_config: SiteConfiguration = (
            self.basic_settings.to_internal()
            | self.status_connection.to_internal()
            | self.configuration_connection.to_internal()
        )
        if self.secret:
            internal_config["secret"] = self.secret
        return internal_config


class SitesApiMgr:
    def __init__(self) -> None:
        self.site_mgmt = SiteManagementFactory().factory()
        self.all_sites = self.site_mgmt.load_sites()

    def get_all_sites(self) -> SiteConfigurations:
        return self.all_sites

    def get_a_site(self, site_id: SiteId) -> SiteConfiguration:
        if not (existing_site := self.all_sites.get(site_id)):
            raise SiteDoesNotExistException
        return existing_site

    def delete_a_site(self, site_id: SiteId) -> None:
        if self.all_sites.get(site_id):
            self.site_mgmt.delete_site(site_id)
        raise SiteDoesNotExistException

    def login_to_site(self, site_id: SiteId, username: str, password: str) -> None:
        site = self.get_a_site(site_id)
        try:
            site["secret"] = do_site_login(site, UserId(username), password)
        except Exception as exc:
            raise LoginException(str(exc))

        self.site_mgmt.save_sites(self.all_sites)

    def logout_of_site(self, site_id: SiteId) -> None:
        site = self.get_a_site(site_id)
        if "secret" in site:
            del site["secret"]
            self.site_mgmt.save_sites(self.all_sites)

    def validate_and_save_site(self, site_id: SiteId, site_config: SiteConfiguration) -> None:
        self.site_mgmt.validate_configuration(site_id, site_config, self.all_sites)
        sites = prepare_raw_site_config(SiteConfigurations({site_id: site_config}))
        self.all_sites.update(sites)
        self.site_mgmt.save_sites(self.all_sites)
