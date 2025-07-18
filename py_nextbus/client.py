from __future__ import annotations

import ua_generator
import json
import logging
from datetime import datetime
from typing import Any
from typing import NamedTuple
from typing import cast

import requests
from requests.exceptions import HTTPError

from py_nextbus.models import AgencyInfo
from py_nextbus.models import RouteDetails
from py_nextbus.models import RouteInfo
from py_nextbus.models import StopPrediction

LOG = logging.getLogger()


class NextBusError(Exception):
    pass


class NextBusHTTPError(NextBusError):
    def __init__(self, message: str, http_err: HTTPError):
        super().__init__()
        self.__dict__.update(http_err.__dict__)
        self.message: str = message


class NextBusValidationError(ValueError, NextBusError):
    """Error with missing fields for a NextBus request."""


class NextBusFormatError(ValueError, NextBusError):
    """Error with parsing a NextBus response."""


class NextBusAuthError(NextBusError):
    """Error with authentication to the NextBus API."""


class RouteStop(NamedTuple):
    route_tag: str
    stop_tag: str | int

    def __str__(self) -> str:
        return f"{self.route_tag}|{self.stop_tag}"

    @classmethod
    def from_dict(cls, legacy_dict: dict[str, str]) -> RouteStop:
        return cls(legacy_dict["route_tag"], legacy_dict["stop_tag"])


class NextBusClient:
    base_url: str = "https://api.prd-1.iq.live.umoiq.com/v2.0/riders"

    def __init__(
        self,
        agency_id: str | None = None,
    ) -> None:
        self.agency_id: str | None = agency_id
        ua = ua_generator.generate()

        self._session: requests.Session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.5",
                "Compress": "true",
                "Connection": "keep-alive",
                "DNT": "1",
                "Origin": "https://rider.umoiq.com",
                "Referer": "https://rider.umoiq.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "User-Agent": ua.headers.get()['user-agent'],
            }
        )

        self._rate_limit: int = 0
        self._rate_limit_remaining: int = 0
        self._rate_limit_reset: datetime | None = None

    @property
    def rate_limit(self) -> int:
        """Returns the rate limit for the API."""
        return self._rate_limit

    @property
    def rate_limit_remaining(self) -> int:
        """Returns the remaining rate limit for the API."""
        return self._rate_limit_remaining

    @property
    def rate_limit_reset(self) -> datetime | None:
        """Returns the time when the rate limit will reset."""
        return self._rate_limit_reset

    @property
    def rate_limit_percent(self) -> float:
        """Returns the percentage of the rate limit remaining."""
        if self.rate_limit == 0:
            return 0.0

        return self.rate_limit_remaining / self.rate_limit * 100

    def agencies(self) -> list[AgencyInfo]:
        return cast(list[AgencyInfo], self._get("agencies"))

    def routes(self, agency_id: str | None = None) -> list[RouteInfo]:
        if not agency_id:
            agency_id = self.agency_id

        return cast(list[RouteInfo], self._get(f"agencies/{agency_id}/routes"))

    def route_details(
        self, route_id: str, agency_id: str | None = None
    ) -> RouteDetails:
        """Includes stops and directions."""
        agency_id = agency_id or self.agency_id
        if not agency_id:
            raise NextBusValidationError("Agency ID is required")

        return cast(RouteDetails, self._get(f"agencies/{agency_id}/routes/{route_id}"))

    def predictions_for_stop(
        self,
        stop_id: str | int,
        route_id: str | None = None,
        direction_id: str | None = None,
        agency_id: str | None = None,
    ) -> list[StopPrediction]:
        """Returns predictions for a stop."""
        agency_id = agency_id or self.agency_id
        if not agency_id:
            raise NextBusValidationError("Agency ID is required")

        if direction_id:
            if not route_id:
                raise NextBusValidationError("Direction ID provided without route ID")

        if route_id:
            predictions = cast(
                list[StopPrediction],
                self._get(
                    f"agencies/{agency_id}/nstops/{route_id}:{stop_id}/predictions"
                ),
            )
        else:
            predictions = cast(
                list[StopPrediction],
                self._get(f"agencies/{agency_id}/stops/{stop_id}/predictions"),
            )

        # If route not provided, return all predictions as the API returned them
        if not route_id:
            return predictions

        # HACK: Filter predictions based on stop and route because the API seems to ignore the route
        predictions = [
            prediction_result
            for prediction_result in predictions
            if (
                prediction_result["stop"]["id"] == stop_id
                and prediction_result["route"]["id"] == route_id
            )
        ]

        # HACK: Filter predictions based on direction in case the API returns extra predictions
        if direction_id:
            for prediction_result in predictions:
                prediction_result["values"] = [
                    prediction
                    for prediction in prediction_result["values"]
                    if prediction["direction"]["id"] == direction_id
                ]

        return predictions

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        if params is None:
            params = {}

        try:
            url = f"{self.base_url}/{endpoint}"
            LOG.debug("GET %s", url)
            response = self._session.get(url, params=params)
            response.raise_for_status()

            # Track rate limit information
            self._rate_limit = int(response.headers.get("X-RateLimit-Limit", 0))
            self._rate_limit_remaining = int(
                response.headers.get("X-RateLimit-Remaining", 0)
            )
            reset_time = response.headers.get("X-RateLimit-Reset")
            self._rate_limit_reset = (
                datetime.fromtimestamp(int(reset_time)) if reset_time else None
            )

            return response.json()

        except HTTPError as exc:
            raise NextBusHTTPError("Error from the NextBus API", exc) from exc
        except json.decoder.JSONDecodeError as exc:
            raise NextBusFormatError("Failed to parse JSON from request") from exc
