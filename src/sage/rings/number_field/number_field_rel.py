r"""
Relative Number Fields

AUTHORS:

- William Stein (2004, 2005): initial version
- Steven Sivek (2006-05-12): added support for relative extensions
- William Stein (2007-09-04): major rewrite and documentation
- Robert Bradshaw (2008-10): specified embeddings into ambient fields
- Nick Alexander (2009-01): modernize coercion implementation

This example follows one in the Magma reference manual::

    sage: K.<y> = NumberField(x^4 - 420*x^2 + 40000)
    sage: z = y^5/11; z
    420/11*y^3 - 40000/11*y
    sage: R.<y> = PolynomialRing(K)
    sage: f = y^2 + y + 1
    sage: L.<a> = K.extension(f); L
    Number Field in a with defining polynomial y^2 + y + 1 over its base field
    sage: KL.<b> = NumberField([x^4 - 420*x^2 + 40000, x^2 + x + 1]); KL
    Number Field in b0 with defining polynomial x^4 - 420*x^2 + 40000 over its base field

We do some arithmetic in a tower of relative number fields::

    sage: K.<cuberoot2> = NumberField(x^3 - 2)
    sage: L.<cuberoot3> = K.extension(x^3 - 3)
    sage: S.<sqrt2> = L.extension(x^2 - 2)
    sage: S
    Number Field in sqrt2 with defining polynomial x^2 - 2 over its base field
    sage: sqrt2 * cuberoot3
    cuberoot3*sqrt2
    sage: (sqrt2 + cuberoot3)^5
    (20*cuberoot3^2 + 15*cuberoot3 + 4)*sqrt2 + 3*cuberoot3^2 + 20*cuberoot3 + 60
    sage: cuberoot2 + cuberoot3
    cuberoot3 + cuberoot2
    sage: cuberoot2 + cuberoot3 + sqrt2
    sqrt2 + cuberoot3 + cuberoot2
    sage: (cuberoot2 + cuberoot3 + sqrt2)^2
    (2*cuberoot3 + 2*cuberoot2)*sqrt2 + cuberoot3^2 + 2*cuberoot2*cuberoot3 + cuberoot2^2 + 2
    sage: cuberoot2 + sqrt2
    sqrt2 + cuberoot2
    sage: a = S(cuberoot2); a
    cuberoot2
    sage: a.parent()
    Number Field in sqrt2 with defining polynomial x^2 - 2 over its base field

WARNING: Doing arithmetic in towers of relative fields that depends on
canonical coercions is currently VERY SLOW.  It is much better to
explicitly coerce all elements into a common field, then do arithmetic
with them there (which is quite fast).

TESTS::

    sage: y = polygen(QQ,'y'); K.<beta> = NumberField([y^3 - 3, y^2 - 2])
    sage: K(y^10)
    27*beta0
"""

#*****************************************************************************
#       Copyright (C) 2004-2009 William Stein <wstein@gmail.com>
#
#  Distributed under the terms of the GNU General Public License (GPL)
#
#    This code is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    General Public License for more details.
#
#  The full text of the GPL is available at:
#
#                  http://www.gnu.org/licenses/
#*****************************************************************************

from __future__ import with_statement
from sage.structure.parent_gens import localvars
from sage.categories.map import Map

import sage.libs.ntl.all as ntl
import sage.libs.pari.all as pari
import sage.interfaces.gap
import sage.misc.preparser
import sage.rings.arith

import sage.rings.complex_field
import sage.rings.real_mpfr
import sage.rings.real_mpfi
import sage.rings.complex_double
import sage.rings.real_double
import sage.rings.real_lazy

from sage.rings.integer_mod import mod

import sage.rings.ring
from sage.misc.latex import latex_variable_name, latex_varify

from class_group import ClassGroup

from sage.structure.element import is_Element
from sage.categories.map import is_Map
from sage.structure.sequence import Sequence

import sage.structure.parent_gens

from sage.structure.proof.proof import get_flag
import maps
import number_field_morphisms
from itertools import count, izip

from sage.rings.integer_ring import IntegerRing

import operator
import weakref
from sage.misc.latex import latex
from sage.misc.cachefunc import cached_method

import sage.rings.arith as arith
import sage.rings.rational_field as rational_field
import sage.rings.integer_ring as integer_ring
import sage.rings.infinity as infinity
import sage.rings.rational as rational
import sage.rings.integer as integer
import sage.rings.polynomial.polynomial_ring as polynomial_ring
import sage.rings.polynomial.polynomial_element as polynomial_element
from sage.rings.polynomial.polynomial_ring_constructor import PolynomialRing
import sage.rings.ideal as ideal
import sage.rings.complex_field
import sage.groups.abelian_gps.abelian_group
import sage.rings.complex_interval_field

from sage.structure.parent_gens import ParentWithGens
import number_field_element
import number_field_element_quadratic
from number_field_ideal import convert_from_zk_basis, NumberFieldIdeal, is_NumberFieldIdeal, NumberFieldFractionalIdeal
from sage.rings.number_field.number_field import NumberField, NumberField_generic, put_natural_embedding_first, proof_flag
from sage.rings.number_field.number_field_base import is_NumberField
from sage.rings.number_field.order import RelativeOrder
from sage.rings.number_field.morphism import RelativeNumberFieldHomomorphism_from_abs
from sage.rings.number_field.number_field_ideal_rel import NumberFieldFractionalIdeal_rel
from sage.libs.all import pari, pari_gen

QQ = rational_field.RationalField()
ZZ = integer_ring.IntegerRing()
RIF = sage.rings.real_mpfi.RealIntervalField()
CIF = sage.rings.complex_interval_field.ComplexIntervalField()
from sage.rings.real_double import RDF
from sage.rings.complex_double import CDF
from sage.rings.real_lazy import RLF, CLF

# from sage.rings.number_field.number_field import is_AbsoluteNumberField
# from sage.rings.number_field.number_field import is_QuadraticField
# from sage.rings.number_field.number_field import is_CyclotomicField

def is_RelativeNumberField(x):
    r"""
    Return True if `x` is a relative number field.

    EXAMPLES::

        sage: from sage.rings.number_field.number_field_rel import is_RelativeNumberField
        sage: is_RelativeNumberField(NumberField(x^2+1,'a'))
        False
        sage: k.<a> = NumberField(x^3 - 2)
        sage: l.<b> = k.extension(x^3 - 3); l
        Number Field in b with defining polynomial x^3 - 3 over its base field
        sage: is_RelativeNumberField(l)
        True
        sage: is_RelativeNumberField(QQ)
        False
    """
    return isinstance(x, NumberField_relative)

class NumberField_relative(NumberField_generic):
    """
    INPUT:

    - ``base`` -- the base field
    - ``polynomial`` -- must be defined in the ring `K[x]`, where `K` is
      the base field.
    - ``name`` -- variable name
    - ``latex_name`` -- latex variable name
    - ``names`` -- alternative to name
    - ``check`` -- whether to check irreducibility of polynomial.

    EXAMPLES::

        sage: K.<a> = NumberField(x^3 - 2)
        sage: t = K['x'].gen()
        sage: L.<b> = K.extension(t^2+t+a); L
        Number Field in b with defining polynomial x^2 + x + a over its base field
    """
    def __init__(self, base, polynomial, name,
                 latex_name=None, names=None, check=True, embedding=None):
        r"""
        INPUT:

        - ``base`` -- the base field
        - ``polynomial`` -- must be defined in the ring `K[x]`, where `K` is
          the base field.
        - ``name`` -- variable name
        - ``latex_name`` -- latex variable name
        - ``names`` -- alternative to name
        - ``check`` -- whether to check irreducibility of polynomial.

        EXAMPLES::

            sage: K.<x> = CyclotomicField(5)[]
            sage: W.<a> = NumberField(x^2 + 1)
            sage: W
            Number Field in a with defining polynomial x^2 + 1 over its base field
            sage: type(W)
            <class 'sage.rings.number_field.number_field_rel.NumberField_relative'>

        Test that check=False really skips the test::

            sage: W.<a> = NumberField(K.cyclotomic_polynomial(5), check=False)
            sage: W
            Number Field in a with defining polynomial x^4 + x^3 + x^2 + x + 1 over its base field

        A relative extension of a relative extension::

            sage: x = ZZ['x'].0
            sage: k.<a> = NumberField([x^2 + 2, x^2 + 1])
            sage: l.<b> = k.extension(x^2 + 3)
            sage: l
            Number Field in b with defining polynomial x^2 + 3 over its base field
            sage: l.base_field()
            Number Field in a0 with defining polynomial x^2 + 2 over its base field
            sage: l.base_field().base_field()
            Number Field in a1 with defining polynomial x^2 + 1

        TESTS:

        Test that irreducibility testing is working::

            sage: x = ZZ['x'].0
            sage: K.<a, b> = NumberField([x^2 + 2, x^2 + 3])
            sage: K.<a> = NumberField(x^2 + 2)
            sage: L.<b> = K.extension(K['x'].0^3 + 3*a)

            sage: (K['x'].0^3 + 2*a).factor()
            (x - a) * (x^2 + a*x - 2)
            sage: L.<b> = K.extension(K['x'].0^3 + 2*a)
            Traceback (most recent call last):
            ...
            ValueError: defining polynomial (x^3 + 2*a) must be irreducible
            sage: (K['x'].0^2 + 2).factor()
            (x - a) * (x + a)
            sage: L.<b> = K.extension(K['x'].0^2 + 2)
            Traceback (most recent call last):
            ...
            ValueError: defining polynomial (x^2 + 2) must be irreducible
            sage: L.<b> = K.extension(x^2 + 2)
            Traceback (most recent call last):
            ...
            ValueError: defining polynomial (x^2 + 2) must be irreducible
        """
        if embedding is not None:
            raise NotImplementedError, "Embeddings not implemented for relative number fields"
        if not names is None: name = names
        if not is_NumberField(base):
            raise TypeError, "base (=%s) must be a number field"%base
        if not isinstance(polynomial, polynomial_element.Polynomial):
            try:
                polynomial = polynomial.polynomial(base)
            except (AttributeError, TypeError), msg:
                raise TypeError, "polynomial (=%s) must be a polynomial."%repr(polynomial)
        if name == base.variable_name():
            raise ValueError, "Base field and extension cannot have the same name"
        if polynomial.parent().base_ring() != base:
            polynomial = polynomial.change_ring(base)
            #raise ValueError, "The polynomial must be defined over the base field"

        # Generate the nf and bnf corresponding to the base field
        # defined as polynomials in y, e.g. for rnfisfree

        # Convert the polynomial defining the base field into a
        # polynomial in y to satisfy PARI's ordering requirements.

        if base.is_relative():
            abs_base = base.absolute_field('a')
            from_abs_base, to_abs_base = abs_base.structure()
        else:
            abs_base = base
            from_abs_base = maps.IdentityMap(base)
            to_abs_base = maps.IdentityMap(base)

        self.__absolute_base_field = abs_base, from_abs_base, to_abs_base
        self.__base_field = base
        self.__relative_polynomial = polynomial
        self._element_class = number_field_element.NumberFieldElement_relative

        if check:
            if not self.pari_relative_polynomial().polisirreducible():
                # this is *much* faster than
                # polynomial.is_irreducible() at some point in the
                # future, is_irreducible should be made faster for
                # polynomials over number fields -- see ticket #4724
                raise ValueError, "defining polynomial (%s) must be irreducible"%polynomial

        self.__gens = [None]

        v = [None]
        K = base
        names = [name]
        while K != QQ:
            names.append(K.variable_name())
            v.append(K.gen())
            K = K.base_field()

        self._assign_names(tuple(names), normalize=False)

        NumberField_generic.__init__(self, self.absolute_polynomial(), name=None,
                                     latex_name=latex_name, check=False, embedding=embedding)

        v[0] = self._gen_relative()
        v = [self(x) for x in v]
        self.__gens = tuple(v)
        self._zero_element = self(0)
        self._one_element =  self(1)

    def change_names(self, names):
        r"""
        Return relative number field isomorphic to self but with the
        given generator names.

        INPUT:

        - ``names`` -- number of names should be at most the number of
          generators of self, i.e., the number of steps in the tower
          of relative fields.

        Also, ``K.structure()`` returns ``from_K`` and ``to_K``, where
        from_K is an isomorphism from `K` to self and ``to_K`` is an
        isomorphism from self to `K`.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: L.<c,d> = K.change_names()
            sage: L
            Number Field in c with defining polynomial x^4 + 3 over its base field
            sage: L.base_field()
            Number Field in d with defining polynomial x^2 + 2

        An example with a 3-level tower::

            sage: K.<a,b,c> = NumberField([x^2 + 17, x^2 + x + 1, x^3 - 2]); K
            Number Field in a with defining polynomial x^2 + 17 over its base field
            sage: L.<m,n,r> = K.change_names()
            sage: L
            Number Field in m with defining polynomial x^2 + 17 over its base field
            sage: L.base_field()
            Number Field in n with defining polynomial x^2 + x + 1 over its base field
            sage: L.base_field().base_field()
            Number Field in r with defining polynomial x^3 - 2

        And a more complicated example::

            sage: PQ.<X> = QQ[]
            sage: F.<a, b> = NumberField([X^2 - 2, X^2 - 3])
            sage: PF.<Y> = F[]
            sage: K.<c> = F.extension(Y^2 - (1 + a)*(a + b)*a*b)
            sage: L.<m, n, r> = K.change_names(); L
            Number Field in m with defining polynomial x^2 + (-2*r - 3)*n - 2*r - 6 over its base field
            sage: L.structure()
            (Isomorphism given by variable name change map:
              From: Number Field in m with defining polynomial x^2 + (-2*r - 3)*n - 2*r - 6 over its base field
              To:   Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field,
             Isomorphism given by variable name change map:
              From: Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              To:   Number Field in m with defining polynomial x^2 + (-2*r - 3)*n - 2*r - 6 over its base field)
        """
        if len(names) == 0:
            names = self.variable_names()
        elif isinstance(names, str):
            names = names.split(',')
        K = self.base_field().change_names(tuple(names[1:]))
        to_K = K.structure()[1]
        old_poly = self.relative_polynomial()
        new_poly = PolynomialRing(K, 'x')([to_K(c) for c in old_poly])
        L = K.extension(new_poly, names=names[0])
        L._set_structure(maps.NameChangeMap(L, self), maps.NameChangeMap(self, L))
        return L

    def subfields(self, degree=0, name=None):
        """
        Return all subfields of this relative number field self of the given degree,
        or of all possible degrees if degree is 0.  The subfields are returned as
        absolute fields together with an embedding into self.  For the case of the
        field itself, the reverse isomorphism is also provided.

        EXAMPLES::

            sage: PQ.<X> = QQ[]
            sage: F.<a, b> = NumberField([X^2 - 2, X^2 - 3])
            sage: PF.<Y> = F[]
            sage: K.<c> = F.extension(Y^2 - (1 + a)*(a + b)*a*b)
            sage: K.subfields(2)
            [
             (Number Field in c0 with defining polynomial x^2 - 48*x + 288, Ring morphism:
              From: Number Field in c0 with defining polynomial x^2 - 48*x + 288
              To:   Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              Defn: c0 |--> 12*a + 24, None),
            (Number Field in c1 with defining polynomial x^2 - 48*x + 192, Ring morphism:
              From: Number Field in c1 with defining polynomial x^2 - 48*x + 192
              To:   Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              Defn: c1 |--> 8*b*a + 24, None),
            (Number Field in c2 with defining polynomial x^2 - 48*x + 384, Ring morphism:
              From: Number Field in c2 with defining polynomial x^2 - 48*x + 384
              To:   Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              Defn: c2 |--> 8*b + 24, None)
            ]
            sage: K.subfields(8, 'w')
            [
             (Number Field in w0 with defining polynomial x^8 - 24*x^6 + 108*x^4 - 144*x^2 + 36, Ring morphism:
              From: Number Field in w0 with defining polynomial x^8 - 24*x^6 + 108*x^4 - 144*x^2 + 36
              To:   Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              Defn: w0 |--> c, Relative number field morphism:
              From: Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              To:   Number Field in w0 with defining polynomial x^8 - 24*x^6 + 108*x^4 - 144*x^2 + 36
              Defn: c |--> w0
                    a |--> 1/12*w0^6 - 11/6*w0^4 + 11/2*w0^2 - 3
                    b |--> -1/24*w0^6 + w0^4 - 17/4*w0^2 + 3)
            ]
            sage: K.subfields(3)
            []
        """
        if name is None:
            name = self.variable_name()
        abs = self.absolute_field(name)
        from_abs, to_abs = abs.structure()
        abs_subfields = abs.subfields(degree=degree)
        ans = []
        for K, from_K, to_K in abs_subfields:
            from_K = K.hom([from_abs(from_K(K.gen()))])
            if to_K != None:
                to_K = RelativeNumberFieldHomomorphism_from_abs(self.Hom(K), to_K*to_abs)
            ans.append((K, from_K, to_K))
        ans = Sequence(ans, immutable=True, cr=ans!=[])
        return ans

    def is_absolute(self):
        r"""
        Returns False, since this is not an absolute field.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: K.is_absolute()
            False
            sage: K.is_relative()
            True
        """
        return False

    def gens(self):
        """
        Return the generators of this relative number field.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: K.gens()
            (a, b)
        """
        return self.__gens

    def ngens(self):
        """
        Return the number of generators of this relative number field.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: K.gens()
            (a, b)
            sage: K.ngens()
            2
        """
        return len(self.__gens)

    def gen(self, n=0):
        """
        Return the `n`'th generator of this relative number field.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: K.gens()
            (a, b)
            sage: K.gen(0)
            a
        """
        if n < 0 or n >= len(self.__gens):
            raise IndexError, "invalid generator %s"%n
        return self.__gens[n]

    def galois_closure(self, names=None):
        r"""
        Return the absolute number field `K` that is the Galois closure of this
        relative number field.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: K.galois_closure('c')
            Number Field in c with defining polynomial x^16 + 144*x^14 + 8988*x^12 + 329616*x^10 + 7824006*x^8 + 113989680*x^6 + 1360354716*x^4 + 3470308272*x^2 + 9407642049
        """
        return self.absolute_field('a').galois_closure(names=names)

    def absolute_degree(self):
        """
        The degree of this relative number field over the rational field.

        EXAMPLES::

            sage: K.<a> = NumberFieldTower([x^2 - 17, x^3 - 2])
            sage: K.absolute_degree()
            6
        """
        return self.absolute_polynomial().degree()

    def relative_degree(self):
        r"""
        Returns the relative degree of this relative number field.

        EXAMPLES::

            sage: K.<a> = NumberFieldTower([x^2 - 17, x^3 - 2])
            sage: K.relative_degree()
            2
        """
        return self.relative_polynomial().degree()

    def degree(self):
        """
        The degree, unqualified, of a relative number field is deliberately
        not implemented, so that a user cannot mistake the absolute degree
        for the relative degree, or vice versa.
        """
        raise NotImplementedError, "For a relative number field you must use relative_degree or absolute_degree as appropriate"

    def maximal_order(self):
        """
        Return the maximal order, i.e., the ring of integers of this
        number field.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^2 + 1, x^2 - 3])
            sage: OK = K.maximal_order(); OK.basis()
            [1, 1/2*a - 1/2*b, -1/2*b*a + 1/2, a]
            sage: charpoly(OK.1)
            x^2 + b*x + 1
            sage: charpoly(OK.2)
            x^2 - x + 1
            sage: O2 = K.order([3*a, 2*b])
            sage: O2.index_in(OK)
            144

        The following was previously "ridiculously slow"; see trac #4738::

            sage: K.<a,b> = NumberField([x^4 + 1, x^4 - 3])
            sage: K.maximal_order()
            Maximal Relative Order in Number Field in a with defining polynomial x^4 + 1 over its base field
        """
        try:
            return self.__maximal_order
        except AttributeError:
            pass
        abs_order = self.absolute_field('z').maximal_order()
        self.__maximal_order = RelativeOrder(self, abs_order, is_maximal=True, check=False)
        return self.__maximal_order

    def __reduce__(self):
        """
        TESTS::

            sage: Z = var('Z')
            sage: K.<w> = NumberField(Z^3 + Z + 1)
            sage: L.<z> = K.extension(Z^3 + 2)
            sage: L = loads(dumps(K))
            sage: print L
            Number Field in w with defining polynomial Z^3 + Z + 1
            sage: print L == K
            True
        """
        return NumberField_relative_v1, (self.__base_field, self.relative_polynomial(), self.variable_name(),
                                          self.latex_variable_name(), self.gen_embedding())

    def _repr_(self):
        """
        Return string representation of this relative number field.

        The base field is not part of the string representation.  To
        find out what the base field is use ``self.base_field()``.

        EXAMPLES::

            sage: k.<a, b> = NumberField([x^5 + 2, x^7 + 3])
            sage: k
            Number Field in a with defining polynomial x^5 + 2 over its base field
            sage: k.base_field()
            Number Field in b with defining polynomial x^7 + 3
        """

        return "Number Field in %s with defining polynomial %s over its base field"%(self.variable_name(), self.relative_polynomial())

        #return "Extension by %s of the Number Field in %s with defining polynomial %s"%(
        #self.polynomial(), self.base_field().variable_name(),
        #    self.base_field().polynomial())

    def _Hom_(self, codomain, cat=None):
        """
        Return homset of homomorphisms from this relative number field
        to the codomain.

        The cat option is currently ignored.   The result is not cached.

        EXAMPLES:
        This function is implicitly called by the Hom method or function.::

            sage: K.<a,b> = NumberField([x^3 - 2, x^2+1])
            sage: K.Hom(K)
            Automorphism group of Number Field in a with defining polynomial x^3 - 2 over its base field
            sage: type(K.Hom(K))
            <class 'sage.rings.number_field.morphism.RelativeNumberFieldHomset_with_category'>
        """

        from number_field import is_NumberFieldHomsetCodomain
        if is_NumberFieldHomsetCodomain(codomain):
            import morphism
            return morphism.RelativeNumberFieldHomset(self, codomain)
        else:
            raise TypeError

    def _latex_(self):
        r"""
        Return a `\LaTeX` representation of the extension.

        EXAMPLES::

            sage: x = QQ['x'].0
            sage: K.<a> = NumberField(x^3 - 2)
            sage: t = K['x'].gen()
            sage: K.extension(t^2+t+a, 'b')._latex_()
            '( \\Bold{Q}[a]/(a^{3} - 2) )[b]/(b^{2} + b + a)'
        """
        return "( %s )[%s]/(%s)"%(latex(self.base_field()), self.latex_variable_name(),
                              self.relative_polynomial()._latex_(self.latex_variable_name()))

    def _coerce_from_other_number_field(self, x):
        """
        Coerce a number field element x into this number field.

        In most cases this currently doesn't work (since it is
        barely implemented) -- it only works for constants.

        INPUT:

        - ``x`` -- an element of some number field

        EXAMPLES::

            sage: K.<a> = NumberField(x^3 + 2)
            sage: L.<b> = NumberField(x^2 + 1)
            sage: K._coerce_from_other_number_field(L(2/3))
            2/3
        """
        if x.parent() is self.base_ring() or x.parent() == self.base_ring():
            return self.__base_inclusion(x)

        f = x.polynomial()
        if f.degree() <= 0:
            return self._element_class(self, f[0])
        # todo: more general coercion if embedding have been asserted
        raise TypeError, "Cannot coerce element into this number field"

    def _coerce_non_number_field_element_in(self, x):
        r"""
        Coerce the non-number field element `x` into this number field.

        INPUT:

        - ``x`` -- a non number field element, e.g., a list,
          integer, rational, or polynomial.

        EXAMPLES::

            sage: K.<a> = NumberField(x^3 + 2/3)
            sage: K._coerce_non_number_field_element_in(-7/8)
            -7/8
            sage: K._coerce_non_number_field_element_in([1,2,3])
            3*a^2 + 2*a + 1

        The list is just turned into a polynomial in the generator.::

            sage: K._coerce_non_number_field_element_in([0,0,0,1,1])
            -2/3*a - 2/3

        Any polynomial whose coefficients can be coerced to rationals will
        coerce, e.g., this one in characteristic 7.::

            sage: f = GF(7)['y']([1,2,3]); f
            3*y^2 + 2*y + 1
            sage: K._coerce_non_number_field_element_in(f)
            3*a^2 + 2*a + 1

        But not this one over a field of order 27.::

            sage: F27.<g> = GF(27)
            sage: f = F27['z']([g^2, 2*g, 1]); f
            z^2 + 2*g*z + g^2
            sage: K._coerce_non_number_field_element_in(f)
            Traceback (most recent call last):
            ...
            TypeError: <class 'sage.rings.polynomial.polynomial_element_generic.Polynomial_generic_dense_field'>

        One can also coerce an element of the polynomial quotient ring
        that is isomorphic to the number field::

            sage: K.<a> = NumberField(x^3 + 17)
            sage: b = K.polynomial_quotient_ring().random_element()
            sage: K(b)
            -1/2*a^2 - 4

        MORE EXAMPLES::

            sage: K.<a> = NumberField(ZZ['x'].0^5 + 2, 'a')
            sage: L.<b> = K.extension(ZZ['x'].0^2 + 3*a, 'b')
            sage: u = QQ['u'].gen()
            sage: t = u.parent()['t'].gen()

            sage: L(a + b)
            b + a

            sage: L(5*t*(1 + u) + 2/3*u)
            (5*a + 5)*b + 2/3*a
            sage: L(0*t + 2/3)
            2/3
            sage: L(1/2*t + 5)
            1/2*b + 5

        This seems reasonable::

            sage: L(t*5)
            5*b

        This is misleading, but correct!  It is more often desired
        to make a number field element given by rational
        coefficients of the relative power basis (so 2*b^2 + 3)
        than it is to create the constant term of such an element,
        which is what would happen if L(u*5) gave 5*a.::

            sage: L(u*5)
            5*b

            sage: L([1, 1/2])
            1/2*b + 1
            sage: L([ a, 1/2 + a/3 ])
            (1/3*a + 1/2)*b + a

            sage: L([ 1 ])
            Traceback (most recent call last):
            ...
            ValueError: Length must be equal to the degree of this number field

        TESTS:
        Examples from Trac ticket \#4727::

            sage: K.<j,b> = QQ[sqrt(-1), sqrt(2)]
            sage: j
            I
            sage: j.list()
            [0, 1]
            sage: K(j.list())
            I
            sage: (b*j + 1/2).list()
            [1/2, sqrt2]
            sage: K((b*j + 1/2).list())
            sqrt2*I + 1/2

        Examples from Trac \#4869::

            sage: K.<z> = CyclotomicField(7)
            sage: Ky.<y> = PolynomialRing(K)
            sage: L.<a> = K.extension(y^2 + 1)
            sage: K(K.polynomial_ring().random_element())
            -12*z^2 + 1/2*z - 1/95
            sage: L(L.polynomial_ring().random_element())
            (z^5 + 1/3*z^4 - z^3 + z^2 - z + 2/3)*a + 1/4*z^5 - 7/2*z^4 + 5/3*z^3 - 1/4*z^2 + 3/2*z - 1

        MORE TESTS:
        We construct the composite of three quadratic fields, then
        coerce from the quartic subfield of the relative extension::

            sage: k.<a,b,c> = NumberField([x^2 + 5, x^2 + 3, x^2 + 1])
            sage: m = k.base_field(); m
            Number Field in b with defining polynomial x^2 + 3 over its base field
            sage: k(m.0)
            b
            sage: k(2/3)
            2/3
            sage: k(m.0^4)
            9

            sage: K.<a> = NumberField(ZZ['x'].0^2 + 2, 'a')
            sage: L.<b> = K.extension(ZZ['x'].0 - a, 'b')
            sage: L(a)
            a
            sage: L(b+a)
            2*a
            sage: K.<a> = NumberField(ZZ['x'].0^5 + 2, 'a')
            sage: L.<b> = K.extension(ZZ['x'].0 - a, 'b')
            sage: L(a)
            a
            sage: L(a**3)
            a^3
            sage: L(a**2+b)
            a^2 + a
            sage: L.<b> = K.extension(ZZ['x'].0 + a/2, 'b')
            sage: L(a)
            a
            sage: L(b)
            -1/2*a
        """
        if isinstance(x, (int, long, rational.Rational,
                              integer.Integer, pari_gen,
                              list)):
            return self._element_class(self, x)
        elif isinstance(x, sage.rings.polynomial.polynomial_quotient_ring_element.PolynomialQuotientRingElement)\
               and (x in self.polynomial_quotient_ring()):
            y = self.polynomial_ring().gen()
            return x.lift().subs({y:self.gen()})
        elif isinstance(x, polynomial_element.Polynomial):
            # we have been given a polynomial, change it to an absolute polynomial
            K = self.base_ring()
            R = self.polynomial_ring()
            if QQ.has_coerce_map_from(x.parent().base_ring()):
                # special case absolute polynomials -- they should be
                # in terms of the relative generator
                x = R(x.list())
            # this should work for base_ring()['x'] and QQ['base']['ext']
            x = self.polynomial_ring()(x)
            f = R( [ K(coeff) for coeff in x.list() ] )
            return self._element_class(self, f(self.gen()).polynomial() )
        else:
            return self._element_class(self, x._rational_())

    def _coerce_map_from_(self, R):
        """
        Canonical coercion of x into this relative number field.

        Currently integers, rationals, the base field, and this field
        itself coerce canonical into this field.

        EXAMPLES::

            sage: S.<y> = NumberField(x^3 + x + 1)
            sage: S.coerce(int(4))
            4
            sage: S.coerce(long(7))
            7
            sage: S.coerce(-Integer(2))
            -2
            sage: z = S.coerce(-7/8); z, type(z)
            (-7/8, <type 'sage.rings.number_field.number_field_element.NumberFieldElement_absolute'>)
            sage: S.coerce(y) is y
            True

        Fields with embeddings into an ambient field coerce naturally.::

            sage: CyclotomicField(15).coerce(CyclotomicField(5).0 - 17/3)
            zeta15^3 - 17/3
            sage: K.<a> = CyclotomicField(16)
            sage: K(CyclotomicField(4).0)
            a^4
            sage: QuadraticField(-3, 'a').coerce_map_from(CyclotomicField(3))
            Generic morphism:
              From: Cyclotomic Field of order 3 and degree 2
              To:   Number Field in a with defining polynomial x^2 + 3
              Defn: zeta3 -> 1/2*a - 1/2

        There are situations for which one might imagine canonical
        coercion could make sense (at least after fixing choices), but
        which are not yet implemented::

            sage: K.<a> = QuadraticField(2)
            sage: K.coerce(sqrt(2))
            Traceback (most recent call last):
            ...
            TypeError: no canonical coercion from Symbolic Ring to Number Field in a with defining polynomial x^2 - 2

        TESTS::

            sage: K.<a> = NumberField(polygen(QQ)^3-2)
            sage: type(K.coerce_map_from(QQ))
            <type 'sage.structure.coerce_maps.DefaultConvertMap_unique'>

        Make sure we still get our optimized morphisms for special fields::

            sage: K.<a> = NumberField(polygen(QQ)^2-2)
            sage: type(K.coerce_map_from(QQ))
            <type 'sage.rings.number_field.number_field_element_quadratic.Q_to_quadratic_field_element'>
        """
        if R in [self, int, long, ZZ, QQ, self.base_field()]:
            return self._generic_convert_map(R)
        from sage.rings.number_field.order import is_NumberFieldOrder
        if is_NumberFieldOrder(R) and R.number_field().has_coerce_map_from(self):
            return self._generic_convert_map(R)
        if is_NumberField(R) and R != QQ:
            if R.coerce_embedding() is not None:
                if self.coerce_embedding() is not None:
                    try:
                        from sage.categories.pushout import pushout
                        ambient_field = pushout(R.coerce_embedding().codomain(), self.coerce_embedding().codomain())
                        if ambient_field is not None:
                            return number_field_morphisms.EmbeddedNumberFieldMorphism(R, self)
                    except (TypeError, ValueError):
                        pass

    def _coerce_map_from_(self, R):
        """
        Canonical implicit coercion of ``R`` into self.

        Elements of this field canonically coerce in, as does anything
        that coerces into the base field of this field.

        EXAMPLES::

            sage: k.<a> = NumberField([x^5 + 2, x^7 + 3])
            sage: b = k(k.base_field().gen())
            sage: b = k.coerce(k.base_field().gen())
            sage: b^7
            -3
            sage: k.coerce(2/3)
            2/3
            sage: c = a + b  # this works
        """
        if R in [int, long, ZZ, QQ, self.base_field()]:
            return self._generic_convert_map(R)
        from sage.rings.number_field.order import is_NumberFieldOrder
        if is_NumberFieldOrder(R) and R.number_field() is self:
            return self._generic_convert_map(R)
        mor = self.base_field().coerce_map_from(R)
        if mor is not None:
            return self.coerce_map_from(self.base_field()) * mor

    def _rnfeltreltoabs(self, element, check=False):
        r"""
        Return PARI's ``rnfeletreltoabs()``, but without requiring ``rnfinit()``.

        TESTS::

            sage: x = ZZ['x'].0
            sage: K.<a> = NumberField(x^2 + 2)
            sage: L.<b> = K.extension(K['x'].0^3 + 3*a)
            sage: M.<c> = L.extension(L['x'].0^2 + 5*b)

            sage: L._rnfeltreltoabs(b^2 + a, check=True)
            -2/9*x^3 - 2
            sage: M._rnfeltreltoabs(c*b, check=True)
            1/625*x^6
        """
        z, a, k = self._pari_rnfequation()
        # a is an alpha in extension such that z(alpha) = base_polynomial(alpha) = 0
        # extension_polynomial(beta) = 0
        # absolute_polynomial(theta) = 0
        # theta = beta + k alpha
        pol = element.polynomial('y')
        t2 = pol(a).lift()
        if check:
            t1 = self.pari_rnf().rnfeltreltoabs(pol._pari_())
            assert t1 == t2
        return t2

    def __base_inclusion(self, element):
        """
        Given an element of the base field, give its inclusion into
        this extension in terms of the generator of this field.

        This is called by the canonical coercion map on elements from
        the base field.

        EXAMPLES::

            sage: k.<a> = NumberField([x^2 + 3, x^2 + 1])
            sage: m = k.base_field(); m
            Number Field in a1 with defining polynomial x^2 + 1
            sage: k._coerce_(m.0 + 2/3)
            a1 + 2/3
            sage: s = k._coerce_(m.0); s
            a1
            sage: s^2
            -1

        This implicitly tests this coercion map::

            sage: K.<a> = NumberField([x^2 + p for p in [5,3,2]])
            sage: K._coerce_(K.base_field().0)
            a1
            sage: K._coerce_(K.base_field().0)^2
            -3
        """
        abs_base, from_abs_base, to_abs_base = self.absolute_base_field()
        # Write element in terms of the absolute base field
        element = self.base_field().coerce(element)
        element = to_abs_base(element)
        # Find an expression in terms of the absolute generator for self of element.
        expr_x = self._rnfeltreltoabs(element)
        # Convert to a Sage polynomial, then to one in gen(), and return it
        R = self.polynomial_ring()
        # We do NOT call self(...) because this code is called by
        # __init__ before we initialize self.gens(), and self(...)
        # uses self.gens()
        return self._element_class(self, R(expr_x))

    def _fractional_ideal_class_(self):
        """
        Return the Python class used to represent ideals of a relative
        number field.

        EXAMPLES::

            sage: k.<a> = NumberField([x^5 + 2, x^7 + 3])
            sage: k._fractional_ideal_class_ ()
            <class 'sage.rings.number_field.number_field_ideal_rel.NumberFieldFractionalIdeal_rel'>
        """
        return sage.rings.number_field.number_field_ideal_rel.NumberFieldFractionalIdeal_rel

    def _pari_base_bnf(self, certify=False, units=True):
        r"""
        Return the PARI bnf (big number field) representation of the
        absolute base field in terms of the pari variable ``y``, suitable
        for extension by the pari variable ``x``.

        All caching is done by the absolute base field.

        INPUT:

        - ``certify`` (bool, default True) -- if True, certify
          correctness of calculations (not assuming GRH).

        EXAMPLES::

            sage: k.<a> = NumberField([x^3 + 2, x^2 + 2])
            sage: k._pari_base_bnf()
            [[;], matrix(0,9), [;], ... 0]
        """
        abs_base, from_abs_base, to_abs_base = self.absolute_base_field()
        bnf_in_x = abs_base.pari_bnf(certify=certify, units=units) # this gives a bnf in terms of x
        x = ZZ['x'].gen()
        y = ZZ['y'].gen()
        bnf_in_y = bnf_in_x.subst(x, y) # now we have a bnf structure in terms of y
        return bnf_in_y

    @cached_method
    def _pari_base_nf(self):
        r"""
        Return the PARI number field representation of the absolute
        base field, in terms of the pari variable ``y``, suitable for
        extension by the pari variable ``x``.

        In future, all caching will be done by the absolute base
        field, but for now we work around a PARI bug that makes
        renamed (substed) nf structures fail in strange ways.

        EXAMPLES::

            sage: y = polygen(QQ,'y')
            sage: k.<a> = NumberField([y^3 + 2, y^2 + 2])
            sage: k._pari_base_nf()
            [y^2 + 2, [0, 1], -8, 1, ..., [1, 0, 0, -2; 0, 1, 1, 0]]
        """
        abs_base, from_abs_base, to_abs_base = self.absolute_base_field()
#         nf_in_x = abs_base.pari_nf() # try to reuse, but this is in terms of x
#         x = ZZ['x'].gen()
#         y = ZZ['y'].gen()
#         nf_in_y = nf_in_x.subst(x, y) # now we have an nf structure in terms of y
        nf_in_y = QQ['y'](abs_base.polynomial())._pari_().nfinit()
        return nf_in_y

    def is_galois(self):
        r"""
        For a relative number field, ``is_galois()`` is deliberately not
        implemented, since it is not clear whether this would mean "Galois over
        `\QQ`" or "Galois over the given base field". Use either ``is_galois_absolute()`` or ``is_galois_relative()`` respectively.

        EXAMPLES::

            sage: k.<a> =NumberField([x^3 - 2, x^2 + x + 1])
            sage: k.is_galois()
            Traceback (most recent call last):
            ...
            NotImplementedError: For a relative number field L you must use either L.is_galois_relative() or L.is_galois_absolute() as appropriate
        """
        raise NotImplementedError, "For a relative number field L you must use either L.is_galois_relative() or L.is_galois_absolute() as appropriate"

    def is_galois_relative(self):
        r"""
        Return True if for this relative extension `L/K`, `L` is a
        Galois extension of `K`.

        EXAMPLE::

            sage: K.<a> = NumberField(x^3 - 2)
            sage: y = polygen(K); L.<b> = K.extension(y^2 - a)
            sage: L.is_galois_relative()
            True
        """
        return self.Hom(self).order() == self.relative_degree()

    def is_galois_absolute(self):
        r"""
        Return True if for this relative extension `L/K`, `L` is a Galois extension of `\QQ`.

        EXAMPLE::

            sage: K.<a> = NumberField(x^3 - 2)
            sage: y = polygen(K); L.<b> = K.extension(y^2 - a)
            sage: L.is_galois_absolute()
            False

        """
        f = self.absolute_polynomial()
        return f.galois_group(pari_group=True).order() == self.absolute_degree()

    def relative_vector_space(self):
        """
        Return vector space over the base field of self and isomorphisms
        from the vector space to self and in the other direction.

        EXAMPLES::

            sage: K.<a,b,c> = NumberField([x^2 + 2, x^3 + 2, x^3 + 3]); K
            Number Field in a with defining polynomial x^2 + 2 over its base field
            sage: V, from_V, to_V = K.relative_vector_space()
            sage: from_V(V.0)
            1
            sage: to_V(K.0)
            (0, 1)
            sage: from_V(to_V(K.0))
            a
            sage: to_V(from_V(V.0))
            (1, 0)
            sage: to_V(from_V(V.1))
            (0, 1)

        The underlying vector space and maps is cached::

            sage: W, from_V, to_V = K.relative_vector_space()
            sage: V is W
            True
        """
        try:
            return self.__relative_vector_space
        except AttributeError:
            pass
        V = self.base_field()**self.relative_degree()
        from_V = maps.MapRelativeVectorSpaceToRelativeNumberField(V, self)
        to_V   = maps.MapRelativeNumberFieldToRelativeVectorSpace(self, V)
        self.__relative_vector_space = (V, from_V, to_V)
        return self.__relative_vector_space

    def absolute_vector_space(self):
        """
        Return vector space over `\QQ` of self and isomorphisms from
        the vector space to self and in the other direction.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^3 + 3, x^3 + 2]); K
            Number Field in a with defining polynomial x^3 + 3 over its base field
            sage: V,from_V,to_V = K.absolute_vector_space(); V
            Vector space of dimension 9 over Rational Field
            sage: from_V
            Isomorphism map:
              From: Vector space of dimension 9 over Rational Field
              To:   Number Field in a with defining polynomial x^3 + 3 over its base field
            sage: to_V
            Isomorphism map:
              From: Number Field in a with defining polynomial x^3 + 3 over its base field
              To:   Vector space of dimension 9 over Rational Field
            sage: c = (a+1)^5; c
            7*a^2 - 10*a - 29
            sage: to_V(c)
            (-29, -712/9, 19712/45, 0, -14/9, 364/45, 0, -4/9, 119/45)
            sage: from_V(to_V(c))
            7*a^2 - 10*a - 29
            sage: from_V(3*to_V(b))
            3*b
        """
        try:
            return self.__absolute_vector_space
        except AttributeError:
            pass
        K = self.absolute_field('a')
        from_K, to_K = K.structure()
        V, from_V, to_V = K.vector_space()
        fr = maps.MapVectorSpaceToRelativeNumberField(V, self, from_V, from_K)
        to   = maps.MapRelativeNumberFieldToVectorSpace(self, V, to_K, to_V)
        ans = (V, fr, to)
        self.__absolute_vector_space = ans
        return ans

    def vector_space(self):
        r"""
        For a relative number field, ``vector_space()`` is
        deliberately not implemented, so that a user cannot confuse
        ``relative_vector_space()`` with ``absolute_vector_space()``.
        """
        raise NotImplementedError, "For a relative number field L you must use either L.relative_vector_space() or L.absolute_vector_space() as appropriate"

    def absolute_base_field(self):
        r"""
        Return the base field of this relative extension, but viewed
        as an absolute field over `\QQ`.

        EXAMPLES::

            sage: K.<a,b,c> = NumberField([x^2 + 2, x^3 + 3, x^3 + 2])
            sage: K
            Number Field in a with defining polynomial x^2 + 2 over its base field
            sage: K.base_field()
            Number Field in b with defining polynomial x^3 + 3 over its base field
            sage: K.absolute_base_field()[0]
            Number Field in a with defining polynomial x^9 + 3*x^6 + 165*x^3 + 1
            sage: K.base_field().absolute_field('z')
            Number Field in z with defining polynomial x^9 + 3*x^6 + 165*x^3 + 1
        """
        return self.__absolute_base_field

    @cached_method
    def _pari_rnfequation(self):
        r"""
        Internal helper that calls PARI's rnfequation for self without
        first initializing any PARI structures.

        TESTS::

            sage: K.<a> = NumberField(x^2 + 2)
            sage: L.<b> = K.extension(K['x'].0^5 + 2*a)
            sage: L._pari_rnfequation()
            [x^10 + 8, Mod(-1/2*x^5, x^10 + 8), 0]
            sage: NumberField(x^10 + 8, 'a').is_isomorphic(L)
            True

        Initialization is lazy enough to allow arithmetic in massive fields::

            sage: K.<a> = NumberField(x^10 + 2000*x + 100001)
            sage: L.<b> = K.extension(K['x'].0^10 + 2*a)
            sage: L._pari_rnfequation()
            [x^100 - 1024000*x^10 + 102401024, Mod(-1/2*x^10, x^100 - 1024000*x^10 + 102401024), 0]
            sage: a + b
            b + a
            sage: b^100
            -2048000*a - 102401024
            sage: (-2*a)^10
            -2048000*a - 102401024
        """
        # Perhaps in future this should check if base_nf is known and
        # use that, since it might be faster.
        return self.pari_absolute_base_polynomial().rnfequation(self.pari_relative_polynomial(), 1)

    @cached_method
    def _gen_relative(self):
        r"""
        Return root of defining polynomial, which is a generator of
        the relative number field over the base.

        EXAMPLES::

            sage: k.<a> = NumberField(x^2+1); k
            Number Field in a with defining polynomial x^2 + 1
            sage: y = polygen(k)
            sage: m.<b> = k.extension(y^2+3); m
            Number Field in b with defining polynomial x^2 + 3 over its base field
            sage: c = m.gen(); c
            b
            sage: c^2 + 3
            0
        """
        rnfeqn = self._pari_rnfequation()
        f = (pari('x') - rnfeqn[2]*rnfeqn[1]).lift()
        g = self._element_class(self, f)
        return g

    def pari_polynomial(self, name='x'):
        """
        PARI polynomial corresponding to the polynomial over the
        rationals that defines this field as an absolute number field.
        By default, this is a polynomial in the variable "x".

        EXAMPLES::

            sage: k.<a, c> = NumberField([x^2 + 3, x^2 + 1])
            sage: k.pari_polynomial()
            x^4 + 8*x^2 + 4
            sage: k.pari_polynomial('a')
            a^4 + 8*a^2 + 4
            sage: k.absolute_polynomial()
            x^4 + 8*x^2 + 4
            sage: k.relative_polynomial()
            x^2 + 3
        """
        try:
            if (self.__pari_polynomial_var == name):
                return self.__pari_polynomial
            else:
                self.__pari_polynomial = self.__pari_polynomial(name)
                self.__pari_polynomial_var = name
                return self.__pari_polynomial
        except AttributeError:
            poly = self.absolute_polynomial()
            with localvars(poly.parent(), name):
                self.__pari_polynomial = poly._pari_()
                self.__pari_polynomial_var = name
            return self.__pari_polynomial

    @cached_method
    def pari_rnf(self):
        r"""
        Return the PARI relative number field object associated
        to this relative extension.

        EXAMPLES::

            sage: k.<a> = NumberField([x^4 + 3, x^2 + 2])
            sage: k.pari_rnf()
            [Mod(1, y^2 + 2)*x^4 + Mod(3, y^2 + 2), [], [[108, 0; 0, 108], [3, 0]~], ... 0]
        """
        return self._pari_base_nf().rnfinit(self.pari_relative_polynomial())

    def pari_absolute_base_polynomial(self):
        r"""
        Return the PARI polynomial defining the absolute base field, in ``y``.

        EXAMPLES::

            sage: x = ZZ['x'].0
            sage: K.<a, b> = NumberField([x^2 + 2, x^2 + 3]); K
            Number Field in a with defining polynomial x^2 + 2 over its base field
            sage: K.pari_absolute_base_polynomial()
            y^2 + 3
            sage: K.pari_absolute_base_polynomial().parent()
            Interface to the PARI C library

            sage: z = ZZ['z'].0
            sage: K.<a, b, c> = NumberField([z^2 + 2, z^2 + 3, z^2 + 5]); K
            Number Field in a with defining polynomial z^2 + 2 over its base field
            sage: K.pari_absolute_base_polynomial()
            y^4 + 16*y^2 + 4
            sage: K.base_field()
            Number Field in b with defining polynomial z^2 + 3 over its base field
            sage: len(QQ['y'](K.pari_absolute_base_polynomial()).roots(K.base_field()))
            4
            sage: K.pari_absolute_base_polynomial().parent()
            Interface to the PARI C library
        """
        abs_base, from_abs_base, to_abs_base = self.absolute_base_field()
        return QQ['y'](abs_base.polynomial())._pari_()

    def pari_relative_polynomial(self):
        r"""
        Return the PARI relative polynomial associated to this number
        field.

        This is always a polynomial in x and y, suitable for PARI's
        rnfinit function.  Notice that if this is a relative extension
        of a relative extension, the base field is the absolute base
        field.

        EXAMPLES::

            sage: k.<i> = NumberField(x^2 + 1)
            sage: m.<z> = k.extension(k['w']([i,0,1]))
            sage: m
            Number Field in z with defining polynomial w^2 + i over its base field
            sage: m.pari_relative_polynomial ()
            Mod(1, y^2 + 1)*x^2 + Mod(y, y^2 + 1)

            sage: l.<t> = m.extension(m['t'].0^2 + z)
            sage: l.pari_relative_polynomial()
            Mod(1, y^4 + 1)*x^2 + Mod(y, y^4 + 1)
        """
        abs_base, _, _ = self.absolute_base_field()
        g = QQ['y'](abs_base.polynomial())
        vals = [ QQ['y'](f.polynomial())._pari_().Mod(g) for f in self.relative_polynomial().list() ]
        f = pari(vals).Polrev()
        return f

    def number_of_roots_of_unity(self):
        """
        Return number of roots of unity in this relative field.

        EXAMPLES::

            sage: K.<a, b> = NumberField( [x^2 + x + 1, x^4 + 1] )
            sage: K.number_of_roots_of_unity()
            24
            sage: K.roots_of_unity()[:5]
            [-b^3*a, b^2*a + b^2, -b, -a, -b^3*a - b^3]
        """
        return self.absolute_field('a').number_of_roots_of_unity()

    def roots_of_unity(self):
        """
        Return all the roots of unity in this relative field, primitive or not.

        EXAMPLES::

            sage: K.<a, b> = NumberField( [x^2 + x + 1, x^4 + 1] )
            sage: K.roots_of_unity()[:5]
            [-b^3*a, b^2*a + b^2, -b, -a, -b^3*a - b^3]
        """
        abs = self.absolute_field('a')
        from_abs, _ = abs.structure()
        return [from_abs(x) for x in abs.roots_of_unity()]

    def absolute_generator(self):
        r"""
        Return the chosen generator over `\QQ` for this relative number field.

        EXAMPLES::

            sage: y = polygen(QQ,'y')
            sage: k.<a> = NumberField([y^2 + 2, y^4 + 3])
            sage: g = k.absolute_generator(); g
            a0 - a1
            sage: g.minpoly()
            x^2 + 2*a1*x + a1^2 + 2
            sage: g.absolute_minpoly()
            x^8 + 8*x^6 + 30*x^4 - 40*x^2 + 49
        """
        try:
            return self.__abs_gen
        except AttributeError:
            self.__abs_gen = self._element_class(self, QQ['x'].gen())
            return self.__abs_gen

    def absolute_field(self, names):
        r"""
        Return an absolute number field `K` that is isomorphic to this
        field along with a field-theoretic bijection from self to `K`
        and from `K` to self.

        INPUT:

        - ``names`` -- string; name of generator of the absolute field

        OUTPUT: an absolute number field

        Also, ``K.structure()`` returns ``from_K`` and ``to_K``, where
        ``from_K`` is an isomorphism from `K` to self and ``to_K`` is
        an isomorphism from self to `K`.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: L.<xyz> = K.absolute_field(); L
            Number Field in xyz with defining polynomial x^8 + 8*x^6 + 30*x^4 - 40*x^2 + 49
            sage: L.<c> = K.absolute_field(); L
            Number Field in c with defining polynomial x^8 + 8*x^6 + 30*x^4 - 40*x^2 + 49

            sage: from_L, to_L = L.structure()
            sage: from_L
            Isomorphism map:
              From: Number Field in c with defining polynomial x^8 + 8*x^6 + 30*x^4 - 40*x^2 + 49
              To:   Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: from_L(c)
            a - b
            sage: to_L
            Isomorphism map:
              From: Number Field in a with defining polynomial x^4 + 3 over its base field
              To:   Number Field in c with defining polynomial x^8 + 8*x^6 + 30*x^4 - 40*x^2 + 49
            sage: to_L(a)
            -5/182*c^7 - 87/364*c^5 - 185/182*c^3 + 323/364*c
            sage: to_L(b)
            -5/182*c^7 - 87/364*c^5 - 185/182*c^3 - 41/364*c
            sage: to_L(a)^4
            -3
            sage: to_L(b)^2
            -2
        """
        try:
            return self.__absolute_field[names]
        except KeyError:
            pass
        except AttributeError:
            self.__absolute_field = {}
        K = NumberField(self.absolute_polynomial(), names, cache=False)
        from_K = maps.MapAbsoluteToRelativeNumberField(K, self)
        to_K = maps.MapRelativeToAbsoluteNumberField(self, K)
        K._set_structure(from_K, to_K)
        self.__absolute_field[names] = K
        return K

    def absolute_polynomial_ntl(self):
        """
        Return defining polynomial of this number field
        as a pair, an ntl polynomial and a denominator.

        This is used mainly to implement some internal arithmetic.

        EXAMPLES::

            sage: NumberField(x^2 + (2/3)*x - 9/17,'a').polynomial_ntl()
            ([-27 34 51], 51)
        """
        try:
            return (self.__abs_polynomial_ntl, self.__abs_denominator_ntl)
        except AttributeError:
            self.__abs_denominator_ntl = ntl.ZZ()
            den = self.absolute_polynomial().denominator()
            self.__abs_denominator_ntl.set_from_sage_int(ZZ(den))
            self.__abs_polynomial_ntl = ntl.ZZX((self.absolute_polynomial()*den).list())
        return (self.__abs_polynomial_ntl, self.__abs_denominator_ntl)

    @cached_method
    def absolute_polynomial(self):
        r"""
        Return the polynomial over `\QQ` that defines this field as an
        extension of the rational numbers.

        EXAMPLES::

            sage: k.<a, b> = NumberField([x^2 + 1, x^3 + x + 1]); k
            Number Field in a with defining polynomial x^2 + 1 over its base field
            sage: k.absolute_polynomial()
            x^6 + 5*x^4 - 2*x^3 + 4*x^2 + 4*x + 1
        """
        return QQ['x'](self._pari_rnfequation()[0])

    def relative_polynomial(self):
        """
        Return the defining polynomial of this relative number field over its base field.

        EXAMPLES::

            sage: K.<a> = NumberFieldTower([x^2 + x + 1, x^3 + x + 1])
            sage: K.relative_polynomial()
            x^2 + x + 1

        Use absolute polynomial for a polynomial that defines the absolute
        extension.::

            sage: K.absolute_polynomial()
            x^6 + 3*x^5 + 8*x^4 + 9*x^3 + 7*x^2 + 6*x + 3
        """
        return self.__relative_polynomial

    def defining_polynomial(self):
        """
        Return the defining polynomial of this relative number field.

        This is exactly the same as ``relative_polynomal()``.

        EXAMPLES::

            sage: C.<z> = CyclotomicField(5)
            sage: PC.<X> = C[]
            sage: K.<a> = C.extension(X^2 + X + z); K
            Number Field in a with defining polynomial X^2 + X + z over its base field
            sage: K.defining_polynomial()
            X^2 + X + z
        """
        return self.relative_polynomial()

    def polynomial(self):
        """
        For a relative number field, ``polynomial()`` is deliberately
        not implemented.  Either ``relative_polynomial()`` or
        ``absolute_polynomial()`` must be used.
        """
        raise NotImplementedError, "For a relative number field L you must use either L.relative_polynomial() or L.absolute_polynomial() as appropriate"

    def base_field(self):
        """
        Return the base field of this relative number field.

        EXAMPLES::

            sage: k.<a> = NumberField([x^3 + x + 1])
            sage: R.<z> = k[]
            sage: L.<b> = NumberField(z^3 + a)
            sage: L.base_field()
            Number Field in a with defining polynomial x^3 + x + 1
            sage: L.base_field() is k
            True

        This is very useful because the print representation of
        a relative field doesn't describe the base field.::

            sage: L
            Number Field in b with defining polynomial z^3 + a over its base field
        """
        return self.__base_field

    def base_ring(self):
        """
        This is exactly the same as base_field.

        EXAMPLES::

            sage: k.<a> = NumberField([x^2 + 1, x^3 + x + 1])
            sage: k.base_ring()
            Number Field in a1 with defining polynomial x^3 + x + 1
            sage: k.base_field()
            Number Field in a1 with defining polynomial x^3 + x + 1
        """
        return self.base_field()

    def embeddings(self, K):
        r"""
        Compute all field embeddings of the relative number field self
        into the field `K` (which need not even be a number field,
        e.g., it could be the complex numbers). This will return an
        identical result when given `K` as input again.

        If possible, the most natural embedding of self into `K`
        is put first in the list.

        INPUT:

        - ``K`` -- a field

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^3 - 2, x^2+1])
            sage: f = K.embeddings(ComplexField(58)); f
            [
            Relative number field morphism:
              From: Number Field in a with defining polynomial x^3 - 2 over its base field
              To:   Complex Field with 58 bits of precision
              Defn: a |--> -0.62996052494743676 - 1.0911236359717214*I
                    b |--> -1.9428902930940239e-16 + 1.0000000000000000*I,
            ...
            Relative number field morphism:
              From: Number Field in a with defining polynomial x^3 - 2 over its base field
              To:   Complex Field with 58 bits of precision
              Defn: a |--> 1.2599210498948731
                    b |--> -0.99999999999999999*I
            ]
            sage: f[0](a)^3
            2.0000000000000002 - 8.6389229103644993e-16*I
            sage: f[0](b)^2
            -1.0000000000000001 - 3.8857805861880480e-16*I
            sage: f[0](a+b)
            -0.62996052494743693 - 0.091123635971721295*I
        """
        try:
            # this should be concordant with automorphisms
            return self.__embeddings[K]
        except AttributeError:
            self.__embeddings = {}
        except KeyError:
            pass
        L = self.absolute_field('a')
        E = L.embeddings(K)
        v = [self.hom(f, K) for f in E]

        # If there is an embedding that preserves variable names
        # then it is most natural, so we put it first.
        put_natural_embedding_first(v)

        self.__embeddings[K] = Sequence(v, cr=v!=[], immutable=True, check=False, universe=self.Hom(K))
        return self.__embeddings[K]

    def automorphisms(self):
        r"""
        Compute all Galois automorphisms of self over the base field.  This is
        different than computing the embeddings of self into self; there,
        automorphisms that do not fix the base field are considered.

        EXAMPLES::

            sage: K.<a, b> = NumberField([x^2 + 10000, x^2 + x + 50]); K
            Number Field in a with defining polynomial x^2 + 10000 over its base field
            sage: K.automorphisms()
            [
            Relative number field endomorphism of Number Field in a with defining polynomial x^2 + 10000 over its base field
              Defn: a |--> a
                    b |--> b,
            Relative number field endomorphism of Number Field in a with defining polynomial x^2 + 10000 over its base field
              Defn: a |--> -a
                    b |--> b
            ]
            sage: rho, tau = K.automorphisms()
            sage: tau(a)
            -a
            sage: tau(b) == b
            True

            sage: L.<b, a> = NumberField([x^2 + x + 50, x^2 + 10000, ]); L
            Number Field in b with defining polynomial x^2 + x + 50 over its base field
            sage: L.automorphisms()
            [
            Relative number field endomorphism of Number Field in b with defining polynomial x^2 + x + 50 over its base field
              Defn: b |--> b
                    a |--> a,
            Relative number field endomorphism of Number Field in b with defining polynomial x^2 + x + 50 over its base field
              Defn: b |--> -b - 1
                    a |--> a
            ]
            sage: rho, tau = L.automorphisms()
            sage: tau(a) == a
            True
            sage: tau(b)
            -b - 1

            sage: PQ.<X> = QQ[]
            sage: F.<a, b> = NumberField([X^2 - 2, X^2 - 3])
            sage: PF.<Y> = F[]
            sage: K.<c> = F.extension(Y^2 - (1 + a)*(a + b)*a*b)
            sage: K.automorphisms()
            [
            Relative number field endomorphism of Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              Defn: c |--> c
                    a |--> a
                    b |--> b,
            Relative number field endomorphism of Number Field in c with defining polynomial Y^2 + (-2*b - 3)*a - 2*b - 6 over its base field
              Defn: c |--> -c
                    a |--> a
                    b |--> b
            ]
        """
        try:
            return self.__automorphisms
        except AttributeError:
            pass

        L = self.absolute_field('a')
        L_into_self, self_into_L = L.structure()
        aas = L.automorphisms() # absolute automorphisms

        a = self_into_L(self.gen())
        abs_base_gens = map(self_into_L, self.base_field().gens())
        v = [ self.hom([ L_into_self(aa(a)) ]) for aa in aas if all(aa(g) == g for g in abs_base_gens) ]
        v.sort()
        put_natural_embedding_first(v)
        self.__automorphisms = Sequence(v, cr = (v != []), immutable=True,
                                        check=False, universe=self.Hom(self))
        return self.__automorphisms

    def places(self, all_complex=False, prec=None):
        """
        Return the collection of all infinite places of self.

        By default, this returns the set of real places as
        homomorphisms into RIF first, followed by a choice of one of
        each pair of complex conjugate homomorphisms into CIF.

        On the other hand, if prec is not None, we simply return places
        into RealField(prec) and ComplexField(prec) (or RDF, CDF if
        prec=53).

        There is an optional flag all_complex, which defaults to False. If
        all_complex is True, then the real embeddings are returned as
        embeddings into CIF instead of RIF.

        EXAMPLES::

            sage: L.<b, c> = NumberFieldTower([x^2 - 5, x^3 + x + 3])
            sage: L.places()
            [Relative number field morphism:
            From: Number Field in b with defining polynomial x^2 - 5 over its base field
            To:   Real Field with 106 bits of precision
            Defn: b |--> -2.236067977499789696409173668937
            c |--> -1.213411662762229634132131377426,
            Relative number field morphism:
            From: Number Field in b with defining polynomial x^2 - 5 over its base field
            To:   Real Field with 106 bits of precision
            Defn: b |--> 2.236067977499789696411548005367
            c |--> -1.213411662762229634130492421800,
            Relative number field morphism:
            From: Number Field in b with defining polynomial x^2 - 5 over its base field
            To:   Complex Field with 53 bits of precision
            Defn: b |--> -2.23606797749979 ...e-1...*I
            c |--> 0.606705831381... - 1.45061224918844*I,
            Relative number field morphism:
            From: Number Field in b with defining polynomial x^2 - 5 over its base field
            To:   Complex Field with 53 bits of precision
            Defn: b |--> 2.23606797749979 - 4.44089209850063e-16*I
            c |--> 0.606705831381115 - 1.45061224918844*I]
        """
        L = self.absolute_field('a')
        pl = L.places(all_complex, prec)
        return [self.hom(p, p.codomain()) for p in pl]


    def absolute_different(self):
        r"""
        Return the absolute different of this relative number field `L`, as an
        ideal of `L`. To get the relative different of `L/K`, use
        ``L.relative_different()``.

        EXAMPLES::

            sage: K.<i> = NumberField(x^2 + 1)
            sage: t = K['t'].gen()
            sage: L.<b> = K.extension(t^4 - i)
            sage: L.absolute_different()
            Fractional ideal (8)
        """
        abs = self.absolute_field('a')
        from_abs = abs.structure()[0]
        return self.ideal([from_abs(g) for g in abs.different().gens()])

    def relative_different(self):
        r"""
        Return the relative different of this extension `L/K` as
        an ideal of `L`.  If you want the absolute different of
        `L/\QQ`, use ``L.absolute_different()``.

        EXAMPLES::

            sage: K.<i> = NumberField(x^2 + 1)
            sage: PK.<t> = K[]
            sage: L.<a> = K.extension(t^4  - i)
            sage: L.relative_different()
            Fractional ideal (4)
        """
        I = self.absolute_different()
        J = self.ideal(self.base_field().absolute_different().gens())
        return  I/J

    def different(self):
        """
        The different, unqualified, of a relative number field is deliberately
        not implemented, so that a user cannot mistake the absolute different
        for the relative different, or vice versa.
        """
        raise NotImplementedError, "For a relative number field you must use relative_different or absolute_different as appropriate"

    def absolute_discriminant(self, v=None):
        r"""
        Return the absolute discriminant of this relative number field
        or if ``v`` is specified, the determinant of the trace pairing
        on the elements of the list ``v``.

        INPUT:

        - ``v`` (optional) -- list of element of this relative number field.

        OUTPUT: Integer if ``v`` is omitted, and Rational otherwise.

        EXAMPLES::

            sage: K.<i> = NumberField(x^2 + 1)
            sage: t = K['t'].gen()
            sage: L.<b> = K.extension(t^4 - i)
            sage: L.absolute_discriminant()
            16777216
            sage: L.absolute_discriminant([(b + i)^j for j in range(8)])
            61911970349056
        """
        abs = self.absolute_field('a')
        if v != None:
            to_abs = abs.structure()[1]
            v = [to_abs(x) for x in v]
        return abs.discriminant(v=v)

    def relative_discriminant(self):
        r"""
        Return the relative discriminant of this extension `L/K` as an ideal of
        `K`. If you want the (rational) discriminant of `L/\QQ`, use e.g.
        ``L.absolute_discriminant()``.

        EXAMPLES::

            sage: K.<i> = NumberField(x^2 + 1)
            sage: t = K['t'].gen()
            sage: L.<b> = K.extension(t^4 - i)
            sage: L.relative_discriminant()
            Fractional ideal (256)
            sage: PQ.<X> = QQ[]
            sage: F.<a, b> = NumberField([X^2 - 2, X^2 - 3])
            sage: PF.<Y> = F[]
            sage: K.<c> = F.extension(Y^2 - (1 + a)*(a + b)*a*b)
            sage: K.relative_discriminant()
            Fractional ideal (-4*b)
        """
        nf = self._pari_base_nf()
        base = self.base_field()
        abs_base = base.absolute_field('a')
        to_base = abs_base.structure()[0]
        D, d = nf.rnfdisc(self.pari_relative_polynomial())
        D = map(abs_base, convert_from_zk_basis(abs_base, D))
        D = map(to_base, D)
        return base.ideal(D)

    def discriminant(self):
        """
        The discriminant, unqualified, of a relative number field is deliberately
        not implemented, so that a user cannot mistake the absolute discriminant
        for the relative discriminant, or vice versa.
        """
        raise NotImplementedError, "For a relative number field you must use relative_discriminant or absolute_discriminant as appropriate"

    def disc(self):
        """
        The discriminant, unqualified, of a relative number field is deliberately
        not implemented, so that a user cannot mistake the absolute discriminant
        for the relative discriminant, or vice versa.
        """
        raise NotImplementedError, "For a relative number field you must use relative_discriminant or absolute_discriminant as appropriate"

    def order(self, *gens, **kwds):
        """
        Return the order with given ring generators in the maximal
        order of this number field.

        INPUT:

        - ``gens`` -- list of elements of self; if no generators are given, just
          returns the cardinality of this number field (oo) for consistency.
        - ``check_is_integral`` -- bool (default: True), whether to check that each
          generator is integral.
        - ``check_rank`` -- bool (default: True), whether to check that the ring
          generated by gens is of full rank.
        - ``allow_subfield`` -- bool (default: False), if True and the generators
          do not generate an order, i.e., they generate a subring of smaller
          rank, instead of raising an error, return an order in a smaller
          number field.

        The check_is_integral and check_rank inputs must be given as
        explicit keyword arguments.

        EXAMPLES::

            sage: P.<a,b,c> = QQ[2^(1/2), 2^(1/3), 3^(1/2)]
            sage: R = P.order([a,b,c]); R
            Relative Order in Number Field in sqrt2 with defining polynomial x^2 - 2 over its base field

        The base ring of an order in a relative extension is still `\ZZ`.:

            sage: R.base_ring()
            Integer Ring

        One must give enough generators to generate a ring of finite index
        in the maximal order::

            sage: P.order([a,b])
            Traceback (most recent call last):
            ...
            ValueError: the rank of the span of gens is wrong
        """
        import sage.rings.number_field.order as order
        if len(gens) == 0:
            return NumberField_generic.order(self)
        if len(gens) == 1 and isinstance(gens[0], (list, tuple)):
            gens = gens[0]
        gens = [self(x) for x in gens]
        return order.relative_order_from_ring_generators(gens, **kwds)


    def galois_group(self, type = 'pari', algorithm='pari', names=None):
        r"""
        Return the Galois group of the Galois closure of this number
        field as an abstract group.  Note that even though this is an
        extension `L/K`, the group will be computed as if it were `L/\QQ`.

        INPUT:

        - ``type`` - ``'pari'`` or ``'gap'``: type of object to return -- a
          wrapper around a Pari or Gap transitive group object.         -

        - algorithm - 'pari', 'kash', 'magma' (default: 'pari', except when
          the degree is >= 12 when 'kash' is tried)

        At present much less functionality is available for Galois groups of
        relative extensions than absolute ones, so try the galois_group method
        of the corresponding absolute field.

        EXAMPLES::

            sage: x = QQ['x'].0
            sage: K.<a> = NumberField(x^2 + 1)
            sage: R.<t> = PolynomialRing(K)
            sage: L = K.extension(t^5-t+a, 'b')
            sage: L.galois_group(type="pari")
            Galois group PARI group [240, -1, 22, "S(5)[x]2"] of degree 10 of the Number Field in b with defining polynomial t^5 - t + a over its base field
        """

        if type is None:
            raise NotImplementedError, "Galois groups of relative extensions not implemented (use the corresponding absolute field)"
        else:
            return self._galois_group_cached(type, algorithm, names)

    def is_free(self, proof=None):
        r"""
        Determine whether or not `L/K` is free (i.e. if `\mathcal{O}_L` is
        a free `\mathcal{O}_K`-module).

        INPUT:

        - ``proof`` -- default: True

        EXAMPLES::

            sage: x = QQ['x'].0
            sage: K.<a> = NumberField(x^2+6)
            sage: L.<b> = K.extension(K['x'].gen()^2 + 3)    ## extend by x^2+3
            sage: L.is_free()
            False
        """
        proof = proof_flag(proof)
        base_bnf = self._pari_base_bnf(proof)
        if base_bnf.rnfisfree(self.pari_relative_polynomial()) == 1:
            return True
        return False

    def lift_to_base(self, element):
        """
        Lift an element of this extension into the base field if possible,
        or raise a ValueError if it is not possible.

        EXAMPLES::

            sage: x = QQ['x'].0
            sage: K = NumberField(x^3 - 2, 'a')
            sage: R = K['x']
            sage: L = K.extension(R.gen()^2 - K.gen(), 'b')
            sage: b = L.gen()
            sage: L.lift_to_base(b^4)
            a^2
            sage: L.lift_to_base(b)
            Traceback (most recent call last):
            ...
            ValueError: The element b is not in the base field
        """
        poly_xy = self.pari_rnf().rnfeltabstorel( self(element)._pari_() )
        str_poly = str(poly_xy)
        if str_poly.find('x') >= 0:
            raise ValueError, "The element %s is not in the base field"%element
        # We convert to a string to avoid some serious nastiness with
        # PARI polynomials secretely thinkining they are in more variables
        # than they are.
        f = QQ['y'](str_poly)
        return self.base_field()(f.list())

    def relativize(self, alpha, names):
        r"""
        Given an element in self or an embedding of a subfield into self,
        return a relative number field `K` isomorphic to self that is relative
        over the absolute field `\QQ(\alpha)` or the domain of `\alpha`, along
        with isomorphisms from `K` to self and from self to `K`.

        INPUT:

        - ``alpha`` -- an element of self, or an embedding of a subfield into self
        - ``names`` -- name of generator for output field `K`.

        OUTPUT: `K` -- a relative number field

        Also, ``K.structure()`` returns ``from_K`` and ``to_K``, where
        ``from_K`` is an isomorphism from `K` to self and ``to_K`` is
        an isomorphism from self to `K`.

        EXAMPLES::

            sage: K.<a,b> = NumberField([x^4 + 3, x^2 + 2]); K
            Number Field in a with defining polynomial x^4 + 3 over its base field
            sage: L.<z,w> = K.relativize(a^2)
            sage: z^2
            z^2
            sage: w^2
            -3
            sage: L
            Number Field in z with defining polynomial x^4 + (-2*w + 4)*x^2 + 4*w + 1 over its base field
            sage: L.base_field()
            Number Field in w with defining polynomial x^2 + 3

        Now suppose we have `K` below `L` below `M`::

            sage: M = NumberField(x^8 + 2, 'a'); M
            Number Field in a with defining polynomial x^8 + 2
            sage: L, L_into_M, _ = M.subfields(4)[0]; L
            Number Field in a0 with defining polynomial x^4 + 2
            sage: K, K_into_L, _ = L.subfields(2)[0]; K
            Number Field in a00 with defining polynomial x^2 + 2
            sage: K_into_M = L_into_M * K_into_L

            sage: L_over_K = L.relativize(K_into_L, 'c'); L_over_K
            Number Field in c0 with defining polynomial x^2 + a00 over its base field
            sage: L_over_K_to_L, L_to_L_over_K = L_over_K.structure()
            sage: M_over_L_over_K = M.relativize(L_into_M * L_over_K_to_L, 'd'); M_over_L_over_K
            Number Field in d0 with defining polynomial x^2 + c0 over its base field
            sage: M_over_L_over_K.base_field() is L_over_K
            True

        Test relativizing a degree 6 field over its degree 2 and degree 3
        subfields, using both an explicit element::

            sage: K.<a> = NumberField(x^6 + 2); K
            Number Field in a with defining polynomial x^6 + 2
            sage: K2, K2_into_K, _ = K.subfields(2)[0]; K2
            Number Field in a0 with defining polynomial x^2 + 2
            sage: K3, K3_into_K, _ = K.subfields(3)[0]; K3
            Number Field in a0 with defining polynomial x^3 - 2

        Here we explicitly relativize over an element of K2 (not the
        generator)::

            sage: L = K.relativize(K3_into_K, 'b'); L
            Number Field in b0 with defining polynomial x^2 + a0 over its base field
            sage: L_to_K, K_to_L = L.structure()
            sage: L_over_K2 = L.relativize(K_to_L(K2_into_K(K2.gen() + 1)), 'c'); L_over_K2
            Number Field in c0 with defining polynomial x^3 - c1 + 1 over its base field
            sage: L_over_K2.base_field()
            Number Field in c1 with defining polynomial x^2 - 2*x + 3

        Here we use a morphism to preserve the base field information::

            sage: K2_into_L = K_to_L * K2_into_K
            sage: L_over_K2 = L.relativize(K2_into_L, 'c'); L_over_K2
            Number Field in c0 with defining polynomial x^3 - a0 over its base field
            sage: L_over_K2.base_field() is K2
            True
        """
        K = self.absolute_field('a')
        from_K, to_K = K.structure()

        if is_Map(alpha):
            # alpha is an embedding of a subfield into self; compose to get an
            # embedding of a subfield into the absolute field
            beta = to_K * alpha
        else:
            # alpha is an element coercible into self
            beta = to_K(alpha)

        S = K.relativize(beta, names)
        # Now S is the appropriate field,
        # but the structure maps attached to S
        # are isomorphisms with the absolute
        # field.  We have to compose them
        # with from_K and to_K to get
        # the appropriate maps.
        from_S, to_S = S.structure()

        # Map from S to self:
        #   x |--> from_K(from_S(x))
        # Map from self to S:
        #   x |--> to_K(from_K(x))
        new_to_S = self.Hom(S)(to_S)
        a = from_S.abs_hom()
        W = a.domain()
        phi = W.hom([from_K(a(W.gen()))])
        new_from_S = S.Hom(self)(phi)
        S._set_structure(new_from_S, new_to_S, unsafe_force_change=True)
        return S

    def uniformizer(self, P, others = "positive"):
        """
        Returns an element of self with valuation 1 at the prime ideal P.

        INPUT:


        -  ``self`` - a number field

        -  ``P`` - a prime ideal of self

        -  ``others`` - either "positive" (default), in which
           case the element will have non-negative valuation at all other
           primes of self, or "negative", in which case the element will have
           non-positive valuation at all other primes of self.


        .. note::

           When P is principal (e.g. always when self has class number
           one) the result may or may not be a generator of P!

        EXAMPLES::

            sage: K.<a, b> = NumberField([x^2 + 23, x^2 - 3])
            sage: P = K.prime_factors(5)[0]; P
            Fractional ideal (5, (-1/2*b + 5/2)*a - 5/2*b - 11/2)
            sage: u = K.uniformizer(P)
            sage: u.valuation(P)
            1
            sage: (P, 1) in K.factor(u)
            True
        """
        if not is_NumberFieldIdeal(P):
            P = self.ideal(P)
        if not P.is_maximal():
            raise ValueError, "P (=%s) must be a nonzero prime."%P
        abs = self.absolute_field('a')
        from_abs = abs.structure()[0]
        return from_abs(abs.uniformizer(P.absolute_ideal(), others=others))


def NumberField_relative_v1(base_field, poly, name, latex_name, canonical_embedding=None):
    """
    This is used in pickling relative fields.

    EXAMPLES::

        sage: from sage.rings.number_field.number_field_rel import NumberField_relative_v1
        sage: R.<x> = CyclotomicField(3)[]
        sage: NumberField_relative_v1(CyclotomicField(3), x^2 + 7, 'a', 'a')
        Number Field in a with defining polynomial x^2 + 7 over its base field
    """
    return NumberField_relative(base_field, poly, name, latex_name, check=False, embedding=canonical_embedding)

NumberField_extension_v1 = NumberField_relative_v1  # historical reasons only
