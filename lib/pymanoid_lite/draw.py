#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Stephane Caron <stephane.caron@normalesup.org>
#
# This file is part of pymanoid.
#
# pymanoid is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# pymanoid is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# pymanoid. If not, see <http://www.gnu.org/licenses/>.

import itertools

from numpy import array, int64, vstack, cross, dot
from pymanoid_lite.toolbox import norm
from scipy.spatial import ConvexHull


def draw_polyhedron(env, points, color=None, plot_type=6, precomp_hull=None,
                    linewidth=1., pointsize=0.02):
    """
    Draw a polyhedron defined as the convex hull of a set of points.

    env -- openravepy environment
    points -- list of 3D points
    color -- RGBA vector
    plot_type -- bitmask with 1 for vertices, 2 for edges and 4 for surface
    precomp_hull -- used in the 2D case where the hull has zero volume
    linewidth -- openravepy format
    pointsize -- openravepy format

    """
    is_2d = precomp_hull is not None
    hull = precomp_hull if precomp_hull is not None else ConvexHull(points)
    vertices = array([points[i] for i in hull.vertices])
    points = array(points)
    color = array(color if color is not None else (0., 0.5, 0., 1.))
    handles = []
    if plot_type & 2:  # include edges
        edge_color = color * 0.7
        edge_color[3] = 1.
        edges = vstack([[points[i], points[j]]
                        for s in hull.simplices
                        for (i, j) in itertools.combinations(s, 2)])
        edges = array(edges)
        handles.append(env.drawlinelist(edges, linewidth=linewidth,
                                        colors=edge_color))
    if plot_type & 4:  # include surface
        if is_2d:
            nv = len(vertices)
            indices = array([(0, i, i + 1) for i in xrange(nv - 1)], int64)
            handles.append(env.drawtrimesh(vertices, indices, colors=color))
        else:
            indices = array(hull.simplices, int64)
            handles.append(env.drawtrimesh(points, indices, colors=color))
    if plot_type & 1:  # vertices
        color[3] = 1.
        handles.append(env.plot3(vertices, pointsize=pointsize, drawstyle=1,
                                 colors=color))
    return handles


def draw_polygon(env, points, n=None, color=None, plot_type=3, linewidth=1.,
                 pointsize=0.02):
    """
    Draw a polygon defined as the convex hull of a set of points. The normal
    vector n of the plane containing the polygon must also be supplied.

    env -- openravepy environment
    points -- list of 3D points
    n -- plane normal vector
    color -- RGBA vector
    plot_type -- bitmask with 1 for edges, 2 for surfaces and 4 for summits
    linewidth -- openravepy format
    pointsize -- openravepy format

    """
    assert n is not None, "Please provide the plane normal as well"
    t1 = array([n[2] - n[1], n[0] - n[2], n[1] - n[0]], dtype=float)
    t1 /= norm(t1)
    t2 = cross(n, t1)
    points2d = [[dot(t1, x), dot(t2, x)] for x in points]
    hull = ConvexHull(points2d)
    return draw_polyhedron(env, points, color, plot_type, hull, linewidth,
                           pointsize)


class ConeCoversFullPlane(Exception):
    pass


def __pick_extreme_rays(rays):
    if len(rays) <= 2:
        return rays
    u_high, u_low = None, rays.pop()
    while u_high is None:
        ray = rays.pop()
        c = cross(u_low, ray)
        if abs(c) < 1e-4:
            continue
        elif c < 0:
            u_low, u_high = ray, u_low
        else:
            u_high = ray
    for u in rays:
        c1 = cross(u_low, u)
        c2 = cross(u_high, u)
        if c1 < 0 and c2 < 0:
            u_low = u
        elif c1 > 0 and c2 > 0:
            u_high = u
        elif c1 < 0 and c2 > 0:
            raise ConeCoversFullPlane
    return u_low, u_high


def __convert_cone2d_to_vertices(vertices, rays, BIG_DIST=1000):
    if not rays:
        return vertices
    r0, r1 = __pick_extreme_rays([r[:2] for r in rays])
    r0 = array([r0[0], r0[1], 0.])
    r1 = array([r1[0], r1[1], 0.])
    r0 = r0 / norm(r0)
    r1 = r1 / norm(r1)
    conv_vertices = [v for v in vertices]
    conv_vertices += [v + r0 * BIG_DIST for v in vertices]
    conv_vertices += [v + r1 * BIG_DIST for v in vertices]
    return conv_vertices


def draw_cone2d(env, vertices, rays, n, color, plot_type):
    """
    Draw a 2D cone defined from its rays and vertices. The normal vector n of
    the plane containing the cone must also be supplied.

    env -- openravepy environment
    vertices -- list of 3D points
    rays -- list of 3D vectors
    n -- plane normal vector
    color -- RGBA vector
    plot_type -- bitmask with 1 for edges, 2 for surfaces and 4 for summits

    """
    if not rays:
        return draw_polygon(
            env, vertices, n, color=color, plot_type=plot_type)
    plot_vertices = __convert_cone2d_to_vertices(vertices, rays)
    return draw_polygon(
        env, plot_vertices, n, color=color, plot_type=plot_type)
