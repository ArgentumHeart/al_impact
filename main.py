import numpy

# SPH equations
from pysph.sph.equation import Group

from pysph.sph.basic_equations import IsothermalEOS, ContinuityEquation, MonaghanArtificialViscosity, \
    XSPHCorrection, VelocityGradient3D

from pysph.sph.solid_mech.basic import MomentumEquationWithStress, HookesDeviatoricStressRate, \
    MonaghanArtificialStress, EnergyEquationWithStress

from pysph.sph.solid_mech.hvi import VonMisesPlasticity2D, MieGruneisenEOS, StiffenedGasEOS

from pysph.sph.gas_dynamics.basic import UpdateSmoothingLengthFromVolume

from pysph.base.utils import get_particle_array
from pysph.base.kernels import Gaussian, CubicSpline, WendlandQuintic
from pysph.solver.application import Application
from pysph.solver.solver import Solver
from pysph.sph.integrator import PECIntegrator, EPECIntegrator
from pysph.sph.integrator_step import SolidMechStep


def add_properties(pa, *props):
    for prop in props:
        pa.add_property(name=prop)


dx = dy = dz = 0.0005  # m
hdx = 1.3

hpr = 0.2 * dx
h = hdx * dx
r = 0.005

ro1 = 2785.0  # refenrence density
C1 = 5328.0  # reference sound-speed
S1 = 1.338  # Particle-shock velocity slope
gamma1 = 2.0  # Gruneisen gamma/parameter
G1 = 2.76e7  # Shear Modulus (kPa)
Yo1 = 0.3e6  # Yield stress
E1 = ro1 * C1 * C1  # Youngs Modulus

ro2 = 2785.0 # reference density
C2 = 5328.0   # reference sound-speed
S2 = 1.338  # Particle shock velocity slope
gamma2 = 2.0  # Gruneisen gamma/parameter
G2 = 2.76e7  # Shear modulus
Yo2 = 0.3e6 # Yield stress
E2 = ro2 * C2 * C2  # Youngs modulus

# general
v_s = 3100.0  # Projectile velocity 3.1 km/s
cs1 = numpy.sqrt(E1 / ro1)  # speed of sound in aluminium
cs2 = numpy.sqrt(E2 / ro2)  # speed of sound in projectile

######################################################################
# SPH constants and parameters

# Monaghan-type artificial viscosity
avisc_alpha = 1.0;
avisc_beta = 1.5;
avisc_eta = 0.1

# XSPH epsilon
xsph_eps = 0.5

# SAV1 artificial viscosity coefficients
alpha1 = 1.0
beta1 = 1.5
eta = 0.1  # in piab equation eta2 was written so final value is 0.01.(as req.)

# SAV2
alpha2 = 2.5
beta2 = 2.5
eta = 0.1  # in piab equation eta2 was written so final value is 0.01.(as req.)

# XSPH
eps = 0.5


######################################################################
# Particle creation rouintes
def get_projectile_particles():
    x, y, z = numpy.mgrid[-0.001:0.001 + dx:dx, -0.005+dx/4:0.005+dx/4 + dx:dx, -0.005+dx/4:0.005+dx/4 + dx:dx]
    x = x.ravel()
    y = y.ravel()
    z = z.ravel()

    d = (z*z + y*y)
    keep = numpy.flatnonzero(d<=r*r)
    x = x[keep]
    y = y[keep]
    z = z[keep]

    x = x - 0.002

    print('%d Projectile particles' % len(x))

    hf = numpy.ones_like(x) * hpr
    mf = numpy.ones_like(x) * dx * dy * dz * ro1
    rhof = numpy.ones_like(x) * ro1
    csf = numpy.ones_like(x) * cs1
    u = numpy.ones_like(x) * v_s

    pa = projectile = get_particle_array(name="projectile", x=x, y=y, z=z, h=hf, m=mf, rho=rhof, cs=csf, u=u)

    # add requisite properties
    # sound speed etc.
    add_properties(pa, 'e')

    # velocity gradient properties
    add_properties(pa, 'v00', 'v01', 'v02', 'v10', 'v11', 'v12', 'v20', 'v21', 'v22')

    # artificial stress properties
    add_properties(pa, 'r00', 'r01', 'r02', 'r11', 'r12', 'r22')

    # deviatoric stress components
    add_properties(pa, 's00', 's01', 's02', 's11', 's12', 's22')

    # deviatoric stress accelerations
    add_properties(pa, 'as00', 'as01', 'as02', 'as11', 'as12', 'as22')

    # deviatoric stress initial values
    add_properties(pa, 's000', 's010', 's020', 's110', 's120', 's220')

    # standard acceleration variables
    add_properties(pa, 'arho', 'au', 'av', 'aw', 'ax', 'ay', 'az', 'ae')

    # initial values
    add_properties(pa, 'rho0', 'u0', 'v0', 'w0', 'x0', 'y0', 'z0', 'e0')

    # load balancing properties
    pa.set_lb_props(list(pa.properties.keys()))

    return projectile


def get_plate_particles():
    x, y, z = numpy.mgrid[0:0.002 + dx:dx, -0.02:0.02 + dx:dx, -0.02:0.02 + dx:dx]
    x = x.ravel()
    y = y.ravel()
    z = z.ravel()

    d = (z * z + y * y)
    keep = numpy.flatnonzero(d <= 0.02 * 0.02)

    x = x[keep]
    y = y[keep]
    z = z[keep]

    print('%d Target particles' % len(x))

    hf = numpy.ones_like(x) * h
    mf = numpy.ones_like(x) * dx * dy * dz * ro1
    rhof = numpy.ones_like(x) * ro1
    csf = numpy.ones_like(x) * cs1
    pa = plate = get_particle_array(name="plate", x=x, y=y, z=z, h=hf, m=mf, rho=rhof, cs=csf)

    # add requisite properties
    # sound speed etc.
    add_properties(pa, 'e')

    # velocity gradient properties
    add_properties(pa, 'v00', 'v01', 'v02', 'v10', 'v11', 'v12', 'v20', 'v21', 'v22')

    # artificial stress properties
    add_properties(pa, 'r00', 'r01', 'r02', 'r11', 'r12', 'r22')

    # deviatoric stress components
    add_properties(pa, 's00', 's01', 's02', 's11', 's12', 's22')

    # deviatoric stress accelerations
    add_properties(pa, 'as00', 'as01', 'as02', 'as11', 'as12', 'as22')

    # deviatoric stress initial values
    add_properties(pa, 's000', 's010', 's020', 's110', 's120', 's220')

    # standard acceleration variables
    add_properties(pa, 'arho', 'au', 'av', 'aw', 'ax', 'ay', 'az', 'ae')

    # initial values
    add_properties(pa, 'rho0', 'u0', 'v0', 'w0', 'x0', 'y0', 'z0', 'e0')

    # load balancing properties
    pa.set_lb_props(list(pa.properties.keys()))

    # removed S_00 and similar components
    plate.v[:] = 0.0
    return plate


class Impact(Application):
    def create_particles(self):
        plate = get_plate_particles()
        projectile = get_projectile_particles()

        return [plate, projectile]

    def create_solver(self):
        dim = 3
        kernel = Gaussian(dim=dim)
        # kernel = WendlandQuintic(dim=dim)

        self.wdeltap = kernel.kernel(rij=dx, h=hdx * dx)

        integrator = EPECIntegrator(projectile=SolidMechStep(), plate=SolidMechStep())

        dt = 5e-10
        tf = 40e-7
        solver = Solver(kernel=kernel, dim=dim, integrator=integrator, dt=dt, tf=tf,
                        output_at_times=numpy.mgrid[0:40e-7:1e-7])

        return solver

    def create_equations(self):
        equations = [

            # update smoothing length
            # Group(
            #     equations = [
            #         UpdateSmoothingLengthFromVolume(dest='plate',      sources=['plate', 'projectile'], dim=dim, k=hdx),
            #         UpdateSmoothingLengthFromVolume(dest='projectile', sources=['plate', 'projectile'], dim=dim, k=hdx),
            #     ],
            #     update_nnps=True,
            # ),

            # compute properties from the current state
            Group(
                equations=[
                    # EOS (compute the pressure using  one of the EOSs)

                    # MieGruneisenEOS(dest='plate',      sources=None, gamma=gamma1, r0=ro1 , c0=C1, S=S1),
                    # MieGruneisenEOS(dest='projectile', sources=None, gamma=gamma2, r0=ro2 , c0=C2, S=S2),

                    StiffenedGasEOS(dest='plate', sources=None, gamma=gamma1, r0=ro1, c0=C1),
                    StiffenedGasEOS(dest='projectile', sources=None, gamma=gamma2, r0=ro2, c0=C2),

                    # compute the velocity gradient tensor
                    VelocityGradient3D(dest='plate', sources=['plate']),
                    VelocityGradient3D(dest='projectile', sources=['projectile']),

                    # # stress
                    VonMisesPlasticity2D(dest='plate', sources=None, flow_stress=Yo1),
                    VonMisesPlasticity2D(dest='projectile', sources=None, flow_stress=Yo2),

                    # # artificial stress to avoid clumping
                    MonaghanArtificialStress(dest='plate', sources=None, eps=0.3),
                    MonaghanArtificialStress(dest='projectile', sources=None, eps=0.3),
                ]
            ),

            # accelerations (rho, u, v, ...)
            Group(
                equations=[

                    # continuity equation
                    ContinuityEquation(dest='plate', sources=['projectile', 'plate']),
                    ContinuityEquation(dest='projectile', sources=['projectile', 'plate']),

                    # momentum equation
                    MomentumEquationWithStress(dest='projectile', sources=['projectile', 'plate', ], n=4,
                                               wdeltap=self.wdeltap),
                    MomentumEquationWithStress(dest='plate', sources=['projectile', 'plate', ], n=4,
                                               wdeltap=self.wdeltap),

                    # energy equation:
                    EnergyEquationWithStress(dest='plate', sources=['projectile', 'plate', ],
                                             alpha=avisc_alpha, beta=avisc_beta, eta=avisc_eta),

                    EnergyEquationWithStress(dest='projectile', sources=['projectile', 'plate', ],
                                             alpha=avisc_alpha, beta=avisc_beta, eta=avisc_eta),

                    # avisc
                    MonaghanArtificialViscosity(dest='plate', sources=['projectile', 'plate'],
                                                alpha=avisc_alpha, beta=avisc_beta),

                    MonaghanArtificialViscosity(dest='projectile', sources=['projectile', 'plate'],
                                                alpha=avisc_alpha, beta=avisc_beta),

                    # updates to the stress term
                    HookesDeviatoricStressRate(dest='plate', sources=None, shear_mod=G1),
                    HookesDeviatoricStressRate(dest='projectile', sources=None, shear_mod=G2),

                    # position stepping
                    XSPHCorrection(dest='plate', sources=['plate'], eps=xsph_eps),
                    XSPHCorrection(dest='projectile', sources=['projectile'], eps=xsph_eps),

                ]
            ),

        ]  # End Group list

        return equations


if __name__ == '__main__':
    app = Impact()
    app.run()
