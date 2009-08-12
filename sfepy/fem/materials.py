from sfepy.base.base import *
from functions import ConstantFunction


##
# 21.07.2006, c
class Materials( Container ):

    def from_conf(conf, functions, wanted=None):
        """Construct Materials instance from configuration."""
        if wanted is None:
            wanted = conf.keys()

        objs = OneTypeList(Material)
        for key, mc in conf.iteritems():
            if key not in wanted: continue

            fun = get_default_attr(mc, 'function', None)
            vals = get_default_attr(mc, 'values', None)
            if (fun is not None) and (vals is not None):
                msg = 'material can have function or values but not both! (%s)' \
                      % mc
                raise ValueError(msg)
            elif vals is not None: # => fun is None
                fun = ConstantFunction(vals, functions = functions)
            else: # => vals is None
                fun = functions[fun]

            if (fun is None):
                msg = 'material has no values! (%s)' % mc
                raise ValueError(msg)

            kind = get_default_attr(mc, 'kind', 'time-dependent')
            mat =  Material(mc.name, mc.region, kind, fun)
            objs.append(mat)

        obj = Materials( objs )
        return obj
    from_conf = staticmethod( from_conf )

    ##
    # 22.08.2006, c
    def setup_regions( self, regions ):
        for mat in self:
            mat.setup_regions( regions )

    def time_update(self, ts, domain, equations, variables):
        output( 'updating materials...' )
        tt = time.clock()
        for mat in self:
            output( ' ', mat.name )
            mat.time_update(ts, domain, equations, variables)
        output( '...done in %.2f s' % (time.clock() - tt) )

##
# 21.07.2006, c
class Material( Struct ):
    """
    A class holding constitutive and other material parameters.

    Example input:

    material_2 = {
       'name' : 'm',
       'region' : 'Omega',
       'values' : {'E' : 1.0},
    }

    Material parameters are passed to terms using the dot notation,
    i.e. 'm.E' in our example case.
    
    """
    def __init__(self, name, region_name, kind, function):
        Struct.__init__(self, name = name,
                        region_name = region_name,
                        kind = kind,
                        function = function)

        self.region = None
        self.datas = None
        self.data = None

    ##
    # 22.08.2006, c
    def setup_regions( self, regions ):
        region = regions[self.region_name]
        self.igs = region.igs
        self.region = region 

    def time_update(self, ts, domain, equations, variables):
        """coors is in region.vertices[ig] order (i.e. sorted by node number)"""
        self.data = None
        if self.datas and (self.kind == 'stationary'): return

        self.datas = {}
        for equation in equations:
            for term in equation.terms:
                names = [ii.split('.')[0] for ii in term.names.material]
                if self.name not in names: continue

                key = (term.region.name, term.integral.name)
                if key in self.datas: continue

                # Any term has at least one variable, all variables used
                # in a term share the same integral.
                var_name = term.names.variable[0]
                var = variables[var_name]

                aps = var.field.aps

                qps = aps.get_physical_qps(self.region, term.integral)
                for ig in self.igs:
                    datas = self.datas.setdefault(key, [])
                    data = self.function(ts, qps.values[ig],
                                        region=self.region, ig=ig)
                    # Restore shape to (n_el, n_qp, ...) until the C
                    # core is rewritten to work with a bunch of physical
                    # point values only.
                    if qps.is_uniform:
                        n_qp = qps.el_indx[ig][1] - qps.el_indx[ig][0]
                        for key, val in data.iteritems():
                            val.shape = (val.shape[0] / n_qp, n_qp,
                                         val.shape[1], val.shape[2])
                    else:
                        raise NotImplementedError
                    datas.append(data)

    ##
    # 31.07.2007, c
    def set_data( self, datas ):
        self.mode = 'user'
        self.datas = datas
        self.data = None

    ##
    # 01.08.2007, c
    def set_function( self, function ):
        self.function = function

    ##
    # 01.08.2007, c
    def set_extra_args( self, extra_args ):
        self.extra_args = extra_args
        
    def get_data( self, key, ig, name ):
        """`name` can be a dict - then a Struct instance with data as
        attributes named as the dict keys is returned."""
##         print 'getting', name

        if isinstance( name, str ):
            return self._get_data( key, ig, name )
        else:
            out = Struct()
            for key, item in name.iteritems():
                setattr( out, key, self._get_data( key, ig, item ) )
            return out
                       
    def _get_data( self, key, ig, name ):
        if name is None:
            msg = 'material arguments must use the dot notation!\n'\
                  '(material: %s, region: %s)' % (self.name, region_name)
            raise ValueError( msg )

        if self.datas is None:
            raise ValueError( 'material data not set! (call time_update())' )

        ii = self.igs.index( ig )
        datas = self.datas[key]

        if isinstance( datas[ii], Struct ):
            return getattr( datas[ii], name )
        else:
            return datas[ii][name]

    ##
    # 01.08.2007, c
    def reduce_on_datas( self, reduce_fun, init = 0.0 ):
        """FIX ME!"""
        out = {}.fromkeys( self.datas[0].keys(), init )

        for data in self.datas:
            for key, val in data.iteritems():
                out[key] = reduce_fun( out[key], val )

        return out
