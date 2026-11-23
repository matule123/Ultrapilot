"""Display-only pinhole map camera. World axes X/Z, height in metres."""
import math


class MapCamera:
    def __init__(self, width, height, centre, heading, radius, elevation=43.0):
        self.width, self.height = float(width), float(height)
        self.cx, self.cz = map(float, centre)
        self.heading = float(heading)
        self.radius = max(1.0, float(radius))
        self.sh, self.ch = math.sin(heading), math.cos(heading)
        self.se, self.ce = math.sin(math.radians(elevation)), math.cos(math.radians(elevation))
        self.distance = self.radius * 2.2
        self.focal = max(1.0, min(width, height)) * 1.10
        self.ahead_offset = self.radius * .48
        self.origin_y = self.height * .43
        self.near = self.radius * .04

    def local(self, point, height=0.0):
        dx, dz = float(point[0])-self.cx, float(point[1])-self.cz
        lateral = dx*self.ch-dz*self.sh
        ahead = -dx*self.sh-dz*self.ch-self.ahead_offset
        depth = self.distance+ahead*self.ce-float(height)*self.se
        up = ahead*self.se+float(height)*self.ce
        return lateral, up, depth

    def project(self, point, height=0.0):
        lateral, up, depth = self.local(point, height)
        if depth < self.near:
            return None
        return (self.width*.5+lateral*self.focal/depth,
                self.origin_y-up*self.focal/depth)

    def ground(self, screen):
        u = (float(screen[0])-self.width*.5)/self.focal
        v = (self.origin_y-float(screen[1]))/self.focal
        denominator = self.se-v*self.ce
        if denominator <= 1e-8:
            return None
        ahead = v*self.distance/denominator
        lateral = u*(self.distance+ahead*self.ce)
        ahead += self.ahead_offset
        return (self.cx+lateral*self.ch-ahead*self.sh,
                self.cz-lateral*self.sh-ahead*self.ch)

    def polygon(self, points, height=0.0):
        """Clip to the near plane before projection; never mirror behind it."""
        vertices = [self.local(p, height) for p in points]
        if len(vertices) < 3:
            return []
        clipped = []
        previous = vertices[-1]
        for current in vertices:
            a, b = previous[2] >= self.near, current[2] >= self.near
            if a != b:
                t = (self.near-previous[2])/(current[2]-previous[2])
                clipped.append(tuple(previous[i]+t*(current[i]-previous[i]) for i in range(3)))
            if b:
                clipped.append(current)
            previous = current
        return [(self.width*.5+x*self.focal/max(self.near,d),
                 self.origin_y-y*self.focal/max(self.near,d)) for x,y,d in clipped]

    def segment(self, first, second):
        a,b=self.local(first),self.local(second)
        if a[2]<self.near and b[2]<self.near:
            return None
        if a[2]<self.near or b[2]<self.near:
            t=(self.near-a[2])/(b[2]-a[2])
            c=tuple(a[i]+t*(b[i]-a[i]) for i in range(3))
            if a[2]<self.near:a=c
            else:b=c
        return [(self.width*.5+x*self.focal/max(self.near,d),
                 self.origin_y-y*self.focal/max(self.near,d)) for x,y,d in (a,b)]

    def ground_matrix(self):
        """Nine QTransform coefficients for the same ground-plane camera.

        Keeping bulk road projection inside Qt avoids per-vertex Python work.
        No Qt import is needed here, so camera math is independently testable.
        """
        dx,dz=-self.ce*self.sh,-self.ce*self.ch
        origin=self.cx*self.sh+self.cz*self.ch-self.ahead_offset
        dc=self.distance+self.ce*origin
        lx,lz,lc=self.ch,-self.sh,-self.cx*self.ch+self.cz*self.sh
        ux,uz,uc=-self.se*self.sh,-self.se*self.ch,self.se*origin
        return (self.width*.5*dx+self.focal*lx,
                self.origin_y*dx-self.focal*ux,dx,
                self.width*.5*dz+self.focal*lz,
                self.origin_y*dz-self.focal*uz,dz,
                self.width*.5*dc+self.focal*lc,
                self.origin_y*dc-self.focal*uc,dc)
