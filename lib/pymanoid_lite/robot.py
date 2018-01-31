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

import time

from errors import RobotNotFound
from numpy import arange, array, cross, dot, eye
from numpy import zeros, hstack, vstack, tensordot
from openravepy import RaveCreateModule
from rotation import crossmat


# Notations and names
# ===================
#
# am: Angular Momentum
# am_rate: Rate (time-derivative) of Angular Momentum
# c: link COM
# m: link mass
# omega: link angular velocity
# r: origin of link frame
# R: link rotation
# T: link transform
# v: link velocity (v = [rd, omega])
#
# Unless otherwise mentioned, coordinates are in the absolute reference frame.


class Robot(object):

    mass = None

    def __init__(self, env, robot_name):
        env.GetPhysicsEngine().SetGravity(array([0, 0, -9.81]))
        rave = env.GetRobot(robot_name)
        if not rave:
            raise RobotNotFound(robot_name)
        q_min, q_max = rave.GetDOFLimits()
        nb_dofs = rave.GetDOF()
        rave.SetDOFVelocityLimits(1000 * rave.GetDOFVelocityLimits())
        rave.SetDOFVelocities([0] * nb_dofs)

        self.active_dofs = None
        self.env = env
        if self.mass is None:  # may not be True for children classes
            self.mass = sum([link.GetMass() for link in rave.GetLinks()])
        self.nb_dofs = nb_dofs
        self.nb_active_dofs = rave.GetDOF()
        self.q_max_full = q_max
        self.q_min_full = q_min
        self.rave = rave

    #
    # Kinematics
    #

    def set_active_dofs(self, active_dofs):
        self.active_dofs = active_dofs
        self.nb_active_dofs = len(active_dofs)
        self.rave.SetActiveDOFs(active_dofs)

    def get_dof_values(self, dof_indices=None):
        if dof_indices is not None:
            return self.rave.GetDOFValues(dof_indices)
        elif self.active_dofs:
            return self.rave.GetActiveDOFValues()
        return self.rave.GetDOFValues()

    def set_dof_values(self, q, dof_indices=None):
        if dof_indices is not None:
            return self.rave.SetDOFValues(q, dof_indices)
        elif self.active_dofs and len(q) == self.nb_active_dofs:
            return self.rave.SetDOFValues(q, self.active_dofs)
        assert len(q) == self.nb_dofs, \
            "DOF mismatch %d v %s" % (len(q), self.nb_dofs)
        return self.rave.SetDOFValues(q)

    @property
    def q(self):
        return self.get_dof_values()

    @property
    def q_full(self):
        return self.rave.GetDOFValues()

    def scale_dof_limits(self, scale=1.):
        q_avg = .5 * (self.q_max_full + self.q_min_full)
        q_dev = .5 * (self.q_max_full - self.q_min_full)
        self.q_max_full = (q_avg + scale * q_dev)
        self.q_min_full = (q_avg - scale * q_dev)

    @property
    def q_max(self):
        if not self.active_dofs:
            return self.q_max_full
        return self.q_max_full[self.active_dofs]

    @property
    def q_min(self):
        if not self.active_dofs:
            return self.q_min_full
        return self.q_min_full[self.active_dofs]

    def get_dof_velocities(self, dof_indices=None):
        if dof_indices is not None:
            return self.rave.GetDOFVelocities(dof_indices)
        elif self.active_dofs:
            return self.rave.GetActiveDOFVelocities()
        return self.rave.GetDOFVelocities()

    def set_dof_velocities(self, qd, dof_indices=None):
        check_dof_limits = 0  # CLA_Nothing
        if dof_indices is not None:
            return self.rave.SetDOFVelocities(qd, check_dof_limits, dof_indices)
        elif self.active_dofs and len(qd) == self.nb_active_dofs:
            return self.rave.SetDOFVelocities(qd, check_dof_limits,
                                              self.active_dofs)
        assert len(qd) == self.nb_dofs
        return self.rave.SetDOFVelocities(qd)

    @property
    def qd(self):
        return self.get_dof_velocities()

    @property
    def qd_full(self):
        return self.rave.GetDOFVelocities()

    #
    # Visualization
    #

    def play_trajectory(self, traj, callback=None, dt=3e-2, dof_indices=None):
        trange = list(arange(0, traj.T, dt))
        for t in trange:
            q = traj.q(t)
            qd = traj.qd(t)
            qdd = traj.qdd(t)
            self.set_dof_values(q, dof_indices)
            if callback:
                callback(t, q, qd, qdd)
            time.sleep(dt)

    def record_trajectory(self, traj, fname='output.mpg', codec=13,
                          framerate=24, width=800, height=600, dt=3e-2):
        viewer = self.env.GetViewer()
        recorder = RaveCreateModule(self.env, 'viewerrecorder')
        self.env.AddModule(recorder, '')
        self.set_dof_values(traj.q(0))
        recorder.SendCommand('Start %d %d %d codec %d timing '
                             'simtime filename %s\n'
                             'viewer %s' % (width, height, framerate, codec,
                                            fname, viewer.GetName()))
        time.sleep(1.)
        self.play_trajectory(traj, dt=dt)
        time.sleep(1.)
        recorder.SendCommand('Stop')
        self.env.Remove(recorder)

    def set_color(self, r, g, b):
        for link in self.rave.GetLinks():
            for geom in link.GetGeometries():
                geom.SetAmbientColor([r, g, b])
                geom.SetDiffuseColor([r, g, b])

    def set_transparency(self, transparency):
        for link in self.rave.GetLinks():
            for geom in link.GetGeometries():
                geom.SetTransparency(transparency)

    #
    # Geometric properties (position level)
    #

    def compute_com(self, q, dof_indices=None):
        total = zeros(3)
        with self.rave:
            self.set_dof_values(q, dof_indices)
            for link in self.rave.GetLinks():
                m = link.GetMass()
                c = link.GetGlobalCOM()
                total += m * c
        return total / self.mass

    @property
    def com(self):
        return self.compute_com(self.q)

    def compute_inertia_matrix(self, q, dof_indices=None, external_torque=None):
        M = zeros((self.nb_dofs, self.nb_dofs))
        self.set_dof_values(q, dof_indices)
        for (i, e_i) in enumerate(eye(self.nb_dofs)):
            tm, _, _ = self.rave.ComputeInverseDynamics(
                e_i, external_torque, returncomponents=True)
            M[:, i] = tm
        return M

    def compute_link_pos(self, link, q, link_coord=None, dof_indices=None):
        with self.rave:
            self.set_dof_values(q, dof_indices)
            T = link.T
            if link_coord is None:
                return T[:3, 3]
            return dot(T, hstack([link_coord, 1]))[:3]

    def compute_link_pose(self, link, q=None, dof_indices=None):
        if q is None:
            return link.pose
        with self.rave:
            self.set_dof_values(q, dof_indices)
            self.rave.SetDOFValues(q, dof_indices)
            return link.pose  # first coefficient will be positive

    #
    # Kinematic properties (velocity level)
    #

    def compute_angular_momentum(self, q, qd, p, dof_indices=None):
        """Compute the angular momentum with respect to point p.

        q -- joint angle values
        qd -- joint-angle velocities
        p -- application point, either a fixed point or the instantaneous COM,
        in world coordinates

        """
        momentum = zeros(3)
        with self.rave:
            self.set_dof_values(q, dof_indices)
            self.set_dof_velocities(qd, dof_indices)
            for link in self.rave.GetLinks():
                T = link.GetTransform()
                R, r = T[0:3, 0:3], T[0:3, 3]
                c_local = link.GetLocalCOM()  # in local RF
                c = r + dot(R, c_local)

                v = link.GetVelocity()
                rd, omega = v[:3], v[3:]
                cd = rd + cross(omega, dot(R, c_local))

                m = link.GetMass()
                I = link.GetLocalInertia()  # in local RF
                momentum += cross(c - p, m * cd) \
                    + dot(R, dot(I, dot(R.T, omega)))
        return momentum

    def compute_cam(self, q, qd, dof_indices=None):
        """
        Compute the centroidal angular momentum (CAM), that is to say, the
        angular momentum with respect to the COM.
        """
        p_G = self.compute_com(q, dof_indices)
        return self.compute_angular_momentum(q, qd, p_G, dof_indices)

    @property
    def cam(self):
        return self.compute_cam(self.q, self.qd)

    def compute_com_velocity(self, q, qd, dof_indices=None):
        total = zeros(3)
        with self.rave:
            self.set_dof_values(q, dof_indices)
            self.set_dof_velocities(qd, dof_indices)
            for link in self.rave.GetLinks():
                m = link.GetMass()
                R = link.GetTransform()[0:3, 0:3]
                c_local = link.GetLocalCOM()
                v = link.GetVelocity()
                rd, omega = v[:3], v[3:]
                cd = rd + cross(omega, dot(R, c_local))
                total += m * cd
        return total / self.mass

    @property
    def comd(self):
        return self.compute_com_velocity(self.q, self.qd)

    #
    # Dynamic properties (acceleration level)
    #

    def compute_cam_rate(self, q, qd, qdd):
        J = self.compute_cam_jacobian(q)
        H = self.compute_cam_hessian(q)
        return dot(J, qdd) + dot(qd, dot(H, qd))

    def compute_com_acceleration(self, q, qd, qdd):
        J = self.compute_com_jacobian(q)
        H = self.compute_com_hessian(q)
        return dot(J, qdd) + dot(qd, dot(H, qdd))

    def compute_zmp(self, q, qd, qdd, dof_indices=None):
        global pb_times, total_times, cum_ratio, avg_ratio
        g = array([0, 0, -9.81])
        f0 = self.mass * g[2]
        tau0 = zeros(3)
        with self.rave:
            self.set_dof_values(q, dof_indices)
            self.set_dof_velocities(qd, dof_indices)
            link_velocities = self.rave.GetLinkVelocities()
            link_accelerations = self.rave.GetLinkAccelerations(qdd)
            for link in self.rave.GetLinks():
                mi = link.GetMass()
                ci = link.GetGlobalCOM()
                I_ci = link.GetLocalInertia()
                Ri = link.GetTransform()[0:3, 0:3]
                ri = dot(Ri, link.GetLocalCOM())
                # linvel = link_velocities[link.GetIndex()][:3]
                angvel = link_velocities[link.GetIndex()][3:]
                linacc = link_accelerations[link.GetIndex()][:3]
                angacc = link_accelerations[link.GetIndex()][3:]
                # ci_dot = linvel + cross(angvel, ri)
                ci_ddot = linacc \
                    + cross(angvel, cross(angvel, ri)) \
                    + cross(angacc, ri)
                angmmt = dot(I_ci, angacc) - cross(dot(I_ci, angvel), angvel)
                f0 -= mi * ci_ddot[2]
                tau0 += mi * cross(ci, g - ci_ddot) - dot(Ri, angmmt)
        return cross(array([0, 0, 1]), tau0) * 1. / f0

    #
    # Jacobians
    #

    def compute_am_jacobian(self, q, p, dof_indices=None):
        """Compute a matrix J(p) such that the angular momentum with respect to
        the point p is

            L_p(q, qd) = dot(J(q), qd).

        q -- joint angle values
        qd -- joint-angle velocities
        p -- application point, either a fixed point or the instantaneous COM,
        in world coordinates

        """
        J = zeros((3, self.nb_dofs))
        with self.rave:
            self.set_dof_values(q, dof_indices)
            for link in self.rave.GetLinks():
                m = link.GetMass()
                i = link.GetIndex()
                c = link.GetGlobalCOM()
                R = link.GetTransform()[0:3, 0:3]
                I = dot(R, dot(link.GetLocalInertia(), R.T))
                J_trans = self.rave.ComputeJacobianTranslation(i, c)
                J_rot = self.rave.ComputeJacobianAxisAngle(i)
                J += dot(crossmat(c - p), m * J_trans) + dot(I, J_rot)
            if dof_indices is not None:
                return J[:, dof_indices]
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return J[:, self.active_dofs]
            return J

    def compute_cam_jacobian(self, q, dof_indices=None):
        """Compute a matrix J(p) such that the angular momentum with respect to
        the center of mass G is

            L_G(q, qd) = dot(J(q), qd).

        q -- joint angle values
        qd -- joint-angle velocities

        """
        p_G = self.compute_com(q, dof_indices)
        return self.compute_am_jacobian(q, p_G, dof_indices)

    def compute_com_jacobian(self, q, dof_indices=None):
        Jcom = zeros((3, self.nb_dofs))
        with self.rave:
            self.set_dof_values(q, dof_indices)
            for link in self.rave.GetLinks():
                index = link.GetIndex()
                com = link.GetGlobalCOM()
                m = link.GetMass()
                J = self.rave.ComputeJacobianTranslation(index, com)
                Jcom += m * J
            J = Jcom / self.mass
            if dof_indices is not None:
                return J[:, dof_indices]
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return J[:, self.active_dofs]
            return J

    def compute_link_jacobian(self, link, q, dof_indices=None):
        with self.rave:
            self.set_dof_values(q, dof_indices)
            J_trans = self.rave.ComputeJacobianTranslation(link.index, link.p)
            J_rot = self.rave.ComputeJacobianAxisAngle(link.index)
            J = vstack([J_rot, J_trans])
            if dof_indices is not None:
                return J[:, dof_indices]
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return J[:, self.active_dofs]
            return J

    def compute_link_pose_jacobian(self, link, q, dof_indices=None):
        with self.rave:
            self.set_dof_values(q, dof_indices)
            J_trans = self.rave.CalculateJacobian(link.index, link.p)
            or_quat = link.rave.GetTransformPose()[:4]  # don't use link.pose
            J_quat = self.rave.CalculateRotationJacobian(link.index, or_quat)
            if or_quat[0] < 0:  # we enforce positive first coefficients
                J_quat *= -1.
            J = vstack([J_quat, J_trans])
            if dof_indices is not None:
                return J[:, dof_indices]
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return J[:, self.active_dofs]
            return J

    def compute_link_translation_jacobian(self, link, q, link_coord=None,
                                          dof_indices=None):
        with self.rave:
            self.set_dof_values(q, dof_indices)
            p = self.compute_link_pos(link, q, link_coord, dof_indices)
            J = self.rave.ComputeJacobianTranslation(link.index, p)
            if dof_indices is not None:
                return J[:, dof_indices]
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return J[:, self.active_dofs]
            return J

    #
    # Hessians
    #

    def compute_am_hessian(self, q, p, dof_indices=None):
        """Returns a matrix H(q) such that the rate of change of the angular
        momentum with respect to point p is

            Ld_p(q, qd) = dot(J(q), qdd) + dot(qd.T, dot(H(q), qd)),

        where J(q) is the result of self.compute_am_jacobian(q, p).

        q -- joint angle values
        qd -- joint-angle velocities
        p -- application point, either a fixed point or the instantaneous COM,
        in world coordinates

        """
        def crosstens(M):
            assert M.shape[0] == 3
            Z = zeros(M.shape[1])
            T = array([[Z, -M[2, :], M[1, :]],
                       [M[2, :], Z, -M[0, :]],
                       [-M[1, :], M[0, :], Z]])
            return T.transpose([2, 0, 1])  # T.shape == (M.shape[1], 3, 3)

        def middot(M, T):
            """Dot product of a matrix with the mid-coordinate of a 3D tensor.

            M -- matrix with shape (n, m)
            T -- tensor with shape (a, m, b)

            Outputs a tensor of shape (a, n, b).

            """
            return tensordot(M, T, axes=(1, 1)).transpose([1, 0, 2])

        H = zeros((self.nb_dofs, 3, self.nb_dofs))
        with self.rave:
            self.set_dof_values(q)
            for link in self.rave.GetLinks():
                m = link.GetMass()
                i = link.GetIndex()
                c = link.GetGlobalCOM()
                R = link.GetTransform()[0:3, 0:3]
                # J_trans = self.rave.ComputeJacobianTranslation(i, c)
                J_rot = self.rave.ComputeJacobianAxisAngle(i)
                H_trans = self.rave.ComputeHessianTranslation(i, c)
                H_rot = self.rave.ComputeHessianAxisAngle(i)
                I = dot(R, dot(link.GetLocalInertia(), R.T))
                H += middot(crossmat(c - p), m * H_trans) \
                    + middot(I, H_rot) \
                    - dot(crosstens(dot(I, J_rot)), J_rot)
            if dof_indices:
                return ((H[dof_indices, :, :])[:, :, dof_indices])
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return ((H[self.active_dofs, :, :])[:, :, self.active_dofs])
            return H

    def compute_cam_hessian(self, q, dof_indices=None):
        """Returns a matrix H(q) such that the rate of change of the angular
        momentum with respect to the center of mass G is

            Ld_G(q, qd) = dot(J(q), qdd) + dot(qd.T, dot(H(q), qd)),

        q -- joint angle values

        """
        p_G = self.compute_com(q)
        return self.compute_am_hessian(q, p_G, dof_indices)

    def compute_com_hessian(self, q, dof_indices=None):
        Hcom = zeros((self.nb_dofs, 3, self.nb_dofs))
        with self.rave:
            self.set_dof_values(q, dof_indices)
            for link in self.rave.GetLinks():
                index = link.GetIndex()
                com = link.GetGlobalCOM()
                m = link.GetMass()
                H = self.rave.ComputeHessianTranslation(index, com)
                Hcom += m * H
            H = Hcom / self.mass
            if dof_indices:
                return ((H[dof_indices, :, :])[:, :, dof_indices])
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return ((H[self.active_dofs, :, :])[:, :, self.active_dofs])
            return H

    def compute_link_hessian(self, link, q, dof_indices=None):
        with self.rave:
            self.set_dof_values(q, dof_indices)
            H_trans = self.rave.ComputeHessianTranslation(link.index, link.p)
            H_rot = self.rave.ComputeHessianAxisAngle(link.index)
            H = hstack([H_rot, H_trans])
            if dof_indices:
                return ((H[dof_indices, :, :])[:, :, dof_indices])
            elif self.active_dofs and len(q) == self.nb_active_dofs:
                return ((H[self.active_dofs, :, :])[:, :, self.active_dofs])
            return H
