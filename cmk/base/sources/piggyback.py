#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from pathlib import Path
from typing import Final, Optional

from cmk.utils.paths import tmp_dir
from cmk.utils.type_defs import HostAddress, HostName, SourceType

from cmk.core_helpers import FetcherType, PiggybackFetcher
from cmk.core_helpers.agent import AgentFileCache, NoCacheFactory
from cmk.core_helpers.piggyback import PiggybackSummarizer

import cmk.base.config as config
from cmk.base.config import HostConfig

from .agent import AgentSource


class PiggybackSource(AgentSource):
    def __init__(
        self,
        host_config: HostConfig,
        ipaddress: Optional[HostAddress],
        *,
        simulation_mode: bool,
        agent_simulator: bool,
    ) -> None:
        super().__init__(
            host_config,
            ipaddress,
            source_type=SourceType.HOST,
            fetcher_type=FetcherType.PIGGYBACK,
            description=PiggybackSource._make_description(host_config.hostname),
            id_="piggyback",
            main_data_source=False,
            simulation_mode=simulation_mode,
            agent_simulator=agent_simulator,
        )
        self.time_settings: Final = config.get_config_cache().get_piggybacked_hosts_time_settings(
            piggybacked_hostname=host_config.hostname
        )

    def _make_file_cache(self) -> AgentFileCache:
        return NoCacheFactory(
            self.host_config.hostname,
            base_path=self.file_cache_base_path,
            simulation=False,  # TODO Quickfix for SUP-9912, should be handled in a better way
            max_age=self.file_cache_max_age,
        ).make()

    def _make_fetcher(self) -> PiggybackFetcher:
        return PiggybackFetcher(
            hostname=self.host_config.hostname,
            address=self.ipaddress,
            time_settings=self.time_settings,
        )

    def _make_summarizer(self) -> PiggybackSummarizer:
        return PiggybackSummarizer(
            self.exit_spec,
            hostname=self.host_config.hostname,
            ipaddress=self.ipaddress,
            time_settings=self.time_settings,
            # Tag: 'Always use and expect piggback data'
            always=self.host_config.is_piggyback_host,
        )

    @staticmethod
    def _make_description(hostname: HostName):
        return "Process piggyback data from %s" % (Path(tmp_dir) / "piggyback" / hostname)
