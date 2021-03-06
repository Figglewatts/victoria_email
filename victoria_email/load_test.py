"""load_test

The functionality of the load testing command.
Allows sending emails to an endpoint at a specified rate for a specified time.

Interfaces with an Azure function on the backend (https://github.com/glasswall-sre/going-postal)
that exposes an HTTP endpoint for sending mail.

The backend will return HTTP 200 in the event of a successful send, and 5xx
otherwise.

Author:
    Sam Gibson <sgibson@glasswallsolutions.com>
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from functools import reduce

import aiohttp
import aiorun

from .schemas import LoadTestConfig


@dataclass
class TestResult:
    """Data class to store the result of a single test.

    Attributes:
        status (int): The HTTP status code returned from the Azure function.
        message (str): The message returned from the Azure function.
        time (datetime): The time this test result was created.
    """
    status: int
    message: str
    time: datetime


async def run_single_test(session: aiohttp.ClientSession, endpoint: str,
                          recipient: str, sender: str,
                          load_test_config: LoadTestConfig) -> TestResult:
    """Asynchronously run a single test by async invoking the backend Azure
    function. Return a TestResult object containing the results of the test.

    Args:
        session: The opened aiohttp session used for all requests.
        endpoint: The SMTP endpoint to send mail to.
        recipient: The email address to send to.
        sender: The email address to send from.
        load_test_config: The config of the load tester.

    Returns:
        TestResult: The result of the test.
    """
    # extract the endpoint and port from the given endpoint
    split_endpoint = endpoint.split(":")
    endpoint = split_endpoint[0]
    port = split_endpoint[1] if len(
        split_endpoint) > 1 else "25"  # default port 25

    # build the request body with the data provided
    req_body = {
        "endpoint": endpoint,
        "port": int(port),
        "tenant_id": str(load_test_config.tenant_id),
        "recipient": recipient,
        "sender": sender,
        "timeout": load_test_config.timeout
    }

    # perform the POST to run the test
    async with session.post(
        load_test_config.mail_send_function_endpoint,
        json=req_body,
        params={"code": load_test_config.mail_send_function_code},
        timeout=aiohttp.ClientTimeout(total=None)) as resp:
        time_now = datetime.now()
        return TestResult(resp.status, await resp.text(), time_now)


async def perform_load_test(frequency: int, endpoint: str, duration: int,
                            recipient: str, sender: str,
                            load_test_config: LoadTestConfig) -> None:
    """Asynchronously run a load test with a given frequency and duration.

    Args:
        frequency: How many tests to run per second.
        endpoint: The SMTP endpoint to send to.
        duration: How long in seconds to run the test.
        recipient: The email address to send to.
        sender: The email address to send with.
        load_test_config: The config for the load tester.
    """
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(
            total=None)) as session:
        # between each test we wait for 1/frequency seconds
        wait_interval = 1.0 / frequency
        number_of_intervals = int(frequency * duration)
        intervals_processed = 0
        tasks = []

        # perform the tests spread out along the time period
        while intervals_processed < number_of_intervals:
            # create a task to run a single test asynchronously
            tasks.append(
                asyncio.create_task(
                    run_single_test(session, endpoint, recipient, sender,
                                    load_test_config)))
            intervals_processed += 1
            percent_done = (intervals_processed / number_of_intervals) * 100
            print(
                f"{intervals_processed} / {number_of_intervals}\t\t\t\t{percent_done:02f}%"
            )
            await asyncio.sleep(wait_interval)

        print("\n")

        # wait for the tasks to complete
        done, _ = await asyncio.wait(tasks,
                                     return_when=asyncio.FIRST_EXCEPTION)
        test_results = []
        for task in done:
            # if there were any exceptions, raise the first one
            err = task.exception()
            if err is not None:
                raise err

            # otherwise add the result to the list
            test_results.append(task.result())

        # compile the amount of successful tests to show the user
        num_successful = reduce(
            lambda cur, result: cur + (1 if result.status == 200 else 0),
            test_results, 0)
        print(
            f"{num_successful} / {number_of_intervals} tests were successfully sent"
        )

        # if there were any non-successful tests, print the reasons
        if num_successful < number_of_intervals:
            print("\n")
            print("Reasons for failures:")
            failed_sends = [
                result for result in test_results if result.status != 200
            ]
            for failed_result in failed_sends:
                print(
                    f"\t{failed_result.time.isoformat()} - {failed_result.status} error - {failed_result.message}"
                )
