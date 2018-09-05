"""Construction of commonly-used product data."""

from typing import Iterable, Dict, Callable, Any, Optional, Hashable, Mapping, List

import numpy as np

from . import options
from .configurations.formulation import Formulation
from .utilities.basics import structure_matrices, extract_matrix, Groups, Array, RecArray


def build_id_data(T: int, J: int, F: int, mergers: Iterable[Dict[Hashable, Hashable]] = ()) -> RecArray:
    """Build a balanced panel of market and firm IDs.

    This function can be used to build `id_data` for :class:`Simulation` initialization.

    Parameters
    ----------
    T : `int`
        Number of markets.
    J : `int`
        Number of products in each market.
    F : `int`
        Number of firms. If `J` is divisible by `F`, firms produce ``J / F`` products in each market. Otherwise, firms
        with smaller IDs will produce excess products.
    mergers : `tuple of dict, optional`
        Each dictionary adds a column of changed firm IDs to the returned matrix of firm IDs. Changed firm IDs are
        identical to the first column of firm IDs, but IDs that are dictionary keys will be replaced with their values,
        which should also be firm IDs between ``0`` and ``F - 1``.

    Returns
    -------
    `recarray`
        IDs that associate products with markets and firms. Each of the ``T * J`` rows corresponds to a product. Fields:

            - **market_ids** : (`object`) - Market IDs that take on values from ``0`` to ``T - 1``.

            - **firm_ids** : (`object`) - Firm IDs that take on values from ``0`` to ``F - 1``. Any columns after the
              first are defined according to `mergers`.

    Example
    -------
    In this example, we'll build a small panel of market and firm IDs with an extra column of firm IDs that represent a
    simple acquisition:

    .. ipython:: python

       @suppress
       np.set_printoptions(linewidth=1)

       id_data = pyblp.build_id_data(T=2, J=5, F=4, mergers=[{2: 0}])
       id_data

    For more examples, refer to the :doc:`Examples </examples>` section.

    """

    # validate the arguments
    if T < 1 or F < 1:
        raise ValueError("Both T and F must be at least 1.")
    if J < F:
        raise ValueError("J must be at least F.")
    for mapping in mergers:
        if not isinstance(mapping, dict):
            raise TypeError("mergers must be a list of dicts.")
        for f1, f2 in mapping.items():
            if not isinstance(f1, int) or not isinstance(f2, int) or not 0 <= f1 <= F - 1 or not 0 <= f2 <= F - 1:
                raise ValueError("dicts in mergers must map from and to firm IDs, which are ints between 0 and F - 1.")

    # build all columns of firm IDs
    firm_ids_list = [np.floor(np.tile(np.arange(J), T) * F / J)]
    for mapping in mergers:
        changed_firm_ids = firm_ids_list[0].copy()
        for f1, f2 in mapping.items():
            changed_firm_ids[changed_firm_ids == f1] = f2
        firm_ids_list.append(changed_firm_ids)

    # build market IDs and structure both sets of IDs
    return structure_matrices({
        'market_ids': (np.repeat(np.arange(T), J).astype(np.int), np.object),
        'firm_ids': (np.stack(firm_ids_list, axis=1).astype(np.int), np.object)
    })


def build_ownership(product_data: Mapping, kappa_specification: Optional[Callable[[Any, Any], float]] = None) -> Array:
    r"""Build ownership matrices, :math:`O`.

    Ownership matrices are defined by their cooperation matrix counterparts, :math:`\kappa`. For each market :math:`t`,
    :math:`O_{jk} = \kappa_{fg}` where :math:`j \in \mathscr{J}_{ft}`, the set of products produced by firm :math:`f` in
    the market, and similarly, :math:`g \in \mathscr{J}_{gt}`.

    Parameters
    ----------
    product_data : `structured array-like`
        Each row corresponds to a product. Markets can have differing numbers of products. The following fields are
        required:

            - **market_ids** : (`object`) - IDs that associate products with markets.

            - **firm_ids** : (`object`) - IDs that associate products with firms. Each column will be used to construct
              one stack of ownership matrices. If there are multiple columns, this field can either be a matrix or it
              can be broken up into multiple one-dimensional fields with column index suffixes that start at zero. For
              example, if there are two columns, this field can be replaced with two one-dimensional fields: `firm_ids0`
              and `firm_ids1`.

    kappa_specification : `callable, optional`
        A function that specifies each market's cooperation matrix, :math:`\kappa`. The function is of the following
        form::

            kappa(f, g) -> value

        where `value` is :math:`O_{jk}` and both `f` and `g` are firm IDs from the `firm_ids` field of `product_data`.

        The default specification, ``lambda: f, g: int(f == g)``, constructs traditional ownership matrices. That is,
        :math:`\kappa = I`, the identify matrix, implies that :math:`O_{jk}` is :math:`1` if the same firm produces
        products :math:`j` and :math:`k`, and is :math:`0` otherwise.

        If `firm_ids` happen to be indices for an actual :math:`\kappa` matrix, ``lambda f, g: kappa[f, g]`` will
        build ownership matrices according to the matrix ``kappa``.

    Returns
    -------
    `ndarray`
        Stacked :math:`J_t \times J_t` ownership matrices, :math:`O`, for each market :math:`t`. Each stack is
        associated with a `firm_ids` column. If a market has fewer products than others, extra columns will contain
        ``numpy.nan``.

    Example
    -------
    In this example, we'll use the IDs created in the example for :func:`build_id_data` to build two stacks of standard
    ownership matrices.

    .. ipython:: python

       @suppress
       np.set_printoptions(threshold=100)

       id_data = pyblp.build_id_data(T=2, J=5, F=4, mergers=[{2: 0}])
       ownership = pyblp.build_ownership(id_data)
       ownership

    We'll now modify the default :math:`\kappa` specification so that the elements associated with firm IDs ``0`` and
    ``1`` are equal to ``0.5``.

    .. ipython:: python

       def kappa_specification(f, g):
           if f == g:
               return 1
           return 0.5 if f < 2 and g < 2 else 0

    Finally, we'll use this specification to build two more stacks of non-standard ownership matrices.

    .. ipython:: python

       @suppress
       np.set_printoptions(threshold=100)

       ownership = pyblp.build_ownership(id_data, kappa_specification)
       ownership

    For more examples, refer to the :doc:`Examples </examples>` section.

    """

    # extract and validate IDs
    market_ids = extract_matrix(product_data, 'market_ids')
    firm_ids = extract_matrix(product_data, 'firm_ids')
    if market_ids is None:
        raise KeyError("product_data must have a market_ids field.")
    if firm_ids is None:
        raise KeyError("product_data must have a firm_ids field.")
    if market_ids.shape[1] > 1:
        raise ValueError("The market_ids field of product_data must be one-dimensional.")

    # validate or use the default kappa specification
    if kappa_specification is None:
        kappa_specification = lambda f, g: np.where(f == g, 1, 0).astype(options.dtype)
    elif callable(kappa_specification):
        kappa_specification = np.vectorize(kappa_specification, [options.dtype])
    if not callable(kappa_specification):
        raise ValueError("kappa_specification must be None or callable.")

    # determine the maximum number of products in a market
    J = np.unique(market_ids, return_counts=True)[1].max()

    # stack ownership matrices vertically for each market and horizontally for each set of firm IDs
    stacks: List[np.ndarray] = []
    for ids in firm_ids.T:
        matrices: List[np.ndarray] = []
        for t in np.unique(market_ids):
            ids_t = ids[market_ids.flat == t]
            tiled_ids_t = np.tile(np.c_[ids_t], ids_t.size)
            ownership_t = np.full((ids_t.size, J), np.nan, options.dtype)
            ownership_t[:, :ids_t.size] = kappa_specification(tiled_ids_t, tiled_ids_t.T)
            matrices.append(ownership_t)
        stacks.append(np.vstack(matrices))
    return np.hstack(stacks)


def build_blp_instruments(formulation: Formulation, product_data: Mapping, firms_index: int = 0) -> Array:
    r"""Construct traditional BLP instruments.

    Traditional BLP instruments are

    .. math:: \mathrm{BLP}(X) = [X, \mathrm{Other}(X), \mathrm{Rival}(X)],

    in which :math:`X` is a matrix of product characteristics, :math:`\mathrm{Rival}(X)` consists of sums over
    characteristics of rival goods, and :math:`\mathrm{Other}(X)` consists of sums over characteristics of other
    non-rival goods. All three matrices have the same dimensions.

    Let :math:`x_{jt}` be the vector of characteristics in :math:`X` for product :math:`j` in market :math:`t`, which is
    produced by firm :math:`f`. That is, :math:`j \in \mathscr{J}_{ft}`. Its counterpart in :math:`\mathrm{Rival}(X)` is

    .. math:: \sum_{r \notin \mathscr{J}_{ft}} x_{rt},

    and its counterpart in :math:`\mathrm{Other}(X)` is

    .. math:: \sum_{r \in \mathscr{J}_{ft} \setminus \{j\}} x_{rt}.

    Parameters
    ----------
    formulation : `Formulation`
        :class:`Formulation` configuration for :math:`X`, the matrix of product characteristics used to build
        instruments. Variable names should correspond to fields in `product_data`.
    product_data : `structured array-like`
        Each row corresponds to a product. Markets can have differing numbers of products. The following fields are
        required:

            - **market_ids** : (`object`) - IDs that associate products with markets.

            - **firm_ids** : (`object`) - IDs that associate products with firms.

        Along with `market_ids` and `firm_ids`, the names of any additional fields can be used as variables in
        `formulation`.
    firms_index : `int, optional`
        Column index of the firm IDs in the `firm_ids` field of `product_data`.

    Returns
    -------
    `ndarray`
        Traditional BLP instruments :math:`\mathrm{BLP}(X)`.

    Example
    -------
    In this example, we'll load the automobile product data from :ref:`Berry, Levinsohn, and Pakes (1995) <blp95>` and
    build some very simple demand-side instruments for the problem. These instruments are different from the pre-built
    ones included in the automobile product data file.

    .. ipython:: python

       formulation = pyblp.Formulation('1 + hpwt + air + mpd + space')
       formulation
       product_data = np.recfromcsv(pyblp.data.BLP_PRODUCTS_LOCATION, encoding='utf-8')
       product_data.dtype.names
       instruments = pyblp.build_blp_instruments(formulation, product_data)
       instruments.shape

    For more examples, refer to the :doc:`Examples </examples>` section.

    """

    # load IDs
    market_ids = extract_matrix(product_data, 'market_ids')
    firm_ids = extract_matrix(product_data, 'firm_ids')
    if market_ids is None or firm_ids is None:
        raise KeyError("product_data must have market_ids and firm_ids fields.")
    if market_ids.shape[1] > 1:
        raise ValueError("The market_ids field of product_data must be one-dimensional.")

    # use only one column of firm IDs
    firm_ids = firm_ids[:, [firms_index]]

    # construct a set of market-firm pair IDs
    paired_ids = market_ids.flatten().astype(np.object)
    paired_ids[:] = list(zip(market_ids, firm_ids))

    # initialize grouping objects
    paired_groups = Groups(paired_ids)
    market_groups = Groups(market_ids)

    # build the instruments
    X = build_matrix(formulation, product_data)
    other = paired_groups.expand(paired_groups.sum(X)) - X
    rival = market_groups.expand(market_groups.sum(X)) - X - other
    return np.ascontiguousarray(np.c_[X, other, rival])


def build_matrix(formulation: Formulation, data: Mapping) -> Array:
    """Construct a matrix according to a formulation.

    Parameters
    ----------
    formulation : `Formulation`
        :class:`Formulation` configuration for the matrix. Variable names should correspond to fields in `data`.
    data : `structured array-like`
        Fields can be used as variables in `formulation`.

    Returns
    -------
    `ndarray`
        The built matrix.

    Example
    -------
    In this example, we'll load the fake cereal data from :ref:`Nevo (2000) <n00>` and build instruments for a problem
    when instead of absorbing product fixed effects, we configure :math:`X_1` to include product indicator variables.
    Specifically, :math:`Z_D` is then product ID indicators followed by the pre-built instruments.

    .. ipython:: python

       instruments_string = ' + '.join(f'demand_instruments{i}' for i in range(20))
       formulation = pyblp.Formulation(f'0 + C(product_ids) + {instruments_string}')
       formulation
       product_data = np.recfromcsv(pyblp.data.NEVO_PRODUCTS_LOCATION, encoding='utf-8')
       product_data.dtype.names
       instruments = pyblp.build_matrix(formulation, product_data)
       instruments.shape

    For more examples, refer to the :doc:`Examples </examples>` section.

    """
    if not isinstance(formulation, Formulation):
        raise TypeError("formulation must be a Formulation instance.")
    return formulation._build_matrix(data)[0]
