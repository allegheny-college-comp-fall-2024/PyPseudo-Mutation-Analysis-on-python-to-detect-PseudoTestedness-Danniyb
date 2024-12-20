"""Sorting algorithms for lists that contain integer values."""

from typing import List

# Reference for some algorithm implementations:
# https://realpython.com/sorting-algorithms-python/

# Add all of the source code based on the above article

# Please develop an intuitive understanding about which of
# these sorting algorithms are fast and which ones are slow. To
# build up this intuitive understand you can read additional
# online articles, check your course text book, and count
# the number of iteration constructs and basic operations.

# Make sure that you add comments to all of these functions
# so as to make it clear that you understand how each step works


def bubble_sort(array: List[int]) -> List[int]:
    """Sort an input list called array using bubble sort."""
    n = len(array)
    for i in range(n):
        for j in range(0, n - i - 1):
            if array[j] > array[j + 1]:
                array[j], array[j + 1] = array[j + 1], array[j]
    return array


def insertion_sort(array: List[int]) -> List[int]:
    """Run an insertion sort on the provided array."""
    for i in range(1, len(array)):
        key = array[i]
        j = i - 1
        while j >= 0 and key < array[j]:
            array[j + 1] = array[j]
            j -= 1
        array[j + 1] = key
    return array


def merge(left: List[int], right: List[int]) -> List[int]:
    """Define a convenience method that supports the merging of lists."""
    merged = []
    while left and right:
        if left[0] <= right[0]:
            merged.append(left.pop(0))
        else:
            merged.append(right.pop(0))
    merged.extend(left or right)
    return merged


def merge_sort(array: List[int]) -> List[int]:
    """Sort the provided list called array with the merge sort algorithm."""
    if len(array) <= 1:
        return array
    mid = len(array) // 2
    left_half = merge_sort(array[:mid])
    right_half = merge_sort(array[mid:])
    return merge(left_half, right_half)


def quick_sort(array: List[int]) -> List[int]:
    """Sort the provided list called array with the quick sort algorithm."""
    if len(array) <= 1:
        return array
    pivot = array[0]
    less_than_pivot = [x for x in array[1:] if x <= pivot]
    greater_than_pivot = [x for x in array[1:] if x > pivot]
    return [*quick_sort(less_than_pivot), pivot, *quick_sort(greater_than_pivot)]


def insertion_sort_tim(array: List[int], left: int = 0, right=None):
    """Use an internal sorting algorithm for the timsort algorithm."""
    if right is None:
        right = len(array) - 1
    for i in range(left + 1, right + 1):
        key = array[i]
        j = i - 1
        while j >= left and array[j] > key:
            array[j + 1] = array[j]
            j -= 1
        array[j + 1] = key


def tim_sort(array: List[int]) -> List[int]:
    """Sort the list called array with the tim sort algorithm using a special insertion sort."""
    RUN = 32
    n = len(array)
    for start in range(0, n, RUN):
        end = min(start + RUN - 1, n - 1)
        insertion_sort_tim(array, start, end)

    size = RUN
    while size < n:
        for left in range(0, n, size * 2):
            mid = min(n - 1, left + size - 1)
            right = min(left + 2 * size - 1, n - 1)
            if mid < right:
                array[left:right + 1] = merge(array[left:mid + 1], array[mid + 1:right + 1])
        size *= 2
    return array
