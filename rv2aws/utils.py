"""Utility functions for the RVTools to AWS Cost Estimator."""

import bisect
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def find_greater_than_or_equal(a, key):
    """
     Find smallest item greater-than or equal to key.
     Raise ValueError if no such item exists.
     If multiple keys are equal, return the leftmost.
     
     Args:
         a: A sorted list
         key: The value to find
         
     Returns:
         The smallest item greater than or equal to key
         
     Raises:
         ValueError: If no such item exists
     """
    assert a and key
    i = bisect.bisect_left(a, key)
    if i == len(a):
        raise ValueError('No item found with key at or above: %r' % (key,))
    return a[i]


def setup_logging(verbose=False):
    """
    Configure logging for the application.
    
    Args:
        verbose: Whether to set logging level to DEBUG
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger()