import logging
from enum import Enum
from typing import Any

import aiohttp
from eth_typing import URI, HexStr
from web3._utils.request import async_json_make_get_request
from web3.beacon import AsyncBeacon
from web3.beacon.api_endpoints import GET_VOLUNTARY_EXITS

from sw_utils.common import urljoin
from sw_utils.exceptions import AiohttpRecoveredErrors

logger = logging.getLogger(__name__)


GET_VALIDATORS = '/eth/v1/beacon/states/{0}/validators{1}'


class ValidatorStatus(Enum):
    """Validator statuses in consensus layer"""

    PENDING_INITIALIZED = 'pending_initialized'
    PENDING_QUEUED = 'pending_queued'
    ACTIVE_ONGOING = 'active_ongoing'
    ACTIVE_EXITING = 'active_exiting'
    ACTIVE_SLASHED = 'active_slashed'
    EXITED_UNSLASHED = 'exited_unslashed'
    EXITED_SLASHED = 'exited_slashed'
    WITHDRAWAL_POSSIBLE = 'withdrawal_possible'
    WITHDRAWAL_DONE = 'withdrawal_done'


PENDING_STATUSES = [ValidatorStatus.PENDING_INITIALIZED, ValidatorStatus.PENDING_QUEUED]
ACTIVE_STATUSES = [
    ValidatorStatus.ACTIVE_ONGOING,
    ValidatorStatus.ACTIVE_EXITING,
    ValidatorStatus.ACTIVE_SLASHED,
]
EXITED_STATUSES = [
    ValidatorStatus.EXITED_UNSLASHED,
    ValidatorStatus.EXITED_SLASHED,
    ValidatorStatus.WITHDRAWAL_POSSIBLE,
    ValidatorStatus.WITHDRAWAL_DONE,
]


class ExtendedAsyncBeacon(AsyncBeacon):
    """
    Extended AsyncBeacon Provider with extra features:
    - support for fallback endpoints
    - single session requests
    - post requests to consensus nodes
    """

    def __init__(
        self,
        base_urls: list[str],
        timeout: int = 60,
        session: aiohttp.ClientSession = None,
    ) -> None:
        self.base_urls = base_urls
        self.timeout = timeout
        self.session = session

        super().__init__('')  # hack origin base_url param

    async def get_validators_by_ids(self, validator_ids: list[str], state_id: str = 'head') -> dict:
        endpoint = GET_VALIDATORS.format(state_id, f"?id={'&id='.join(validator_ids)}")
        return await self._async_make_get_request(endpoint)

    async def submit_voluntary_exit(
        self, epoch: int, validator_index: int, signature: HexStr
    ) -> None:
        data = {
            'message': {'epoch': str(epoch), 'validator_index': str(validator_index)},
            'signature': signature,
        }
        for i, url in enumerate(self.base_urls):
            try:
                uri = URI(urljoin(url, GET_VOLUNTARY_EXITS))

                async with aiohttp.ClientSession() as session:
                    async with session.post(uri, json=data) as response:
                        response.raise_for_status()
                        return

            except AiohttpRecoveredErrors as error:
                if i == len(self.base_urls) - 1:
                    raise error
                logger.error('%s: %s', url, repr(error))

    async def _async_make_get_request(self, endpoint_uri: str) -> dict[str, Any]:
        for i, url in enumerate(self.base_urls):
            try:
                uri = URI(urljoin(url, endpoint_uri))
                if self.session:
                    return await self._make_session_get_request(uri)
                return await async_json_make_get_request(uri, timeout=self.timeout)

            except AiohttpRecoveredErrors as error:
                if i == len(self.base_urls) - 1:
                    raise error
                logger.error('%s: %s', url, repr(error))

        return {}

    async def _make_session_get_request(self, uri):
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        logger.debug('GET %s', uri)

        async with self.session.get(uri, timeout=timeout) as response:
            response.raise_for_status()
            data = await response.json()
            return data


def get_consensus_client(
    endpoints: list[str], timeout: int = 60, session: aiohttp.ClientSession = None
) -> ExtendedAsyncBeacon:
    return ExtendedAsyncBeacon(base_urls=endpoints, timeout=timeout, session=session)
