/** Map maths for the offline area map. No tiles or external services: pins are drawn over the coverage circle. */
const METRES_PER_DEG_LAT=111_320;

export interface Centre {center_lat:number; center_lon:number; radius_m:number}

/** Latitude/longitude to a point in [0, size], centred on the locality and scaled so the radius touches the edge. */
export function project(c:Centre,lat:number,lon:number,size=400){
  const east=(lon-c.center_lon)*METRES_PER_DEG_LAT*Math.cos(c.center_lat*Math.PI/180);
  const north=(lat-c.center_lat)*METRES_PER_DEG_LAT;
  return {x:size/2+(east/c.radius_m)*(size/2),y:size/2-(north/c.radius_m)*(size/2)};
}

export function unproject(c:Centre,x:number,y:number,size=400){
  const east=((x-size/2)/(size/2))*c.radius_m;
  const north=-((y-size/2)/(size/2))*c.radius_m;
  return {
    lat:c.center_lat+north/METRES_PER_DEG_LAT,
    lon:c.center_lon+east/(METRES_PER_DEG_LAT*Math.cos(c.center_lat*Math.PI/180)),
  };
}

export function distanceM(lat1:number,lon1:number,lat2:number,lon2:number){
  const rad=Math.PI/180,dPhi=(lat2-lat1)*rad,dLam=(lon2-lon1)*rad;
  const a=Math.sin(dPhi/2)**2+Math.cos(lat1*rad)*Math.cos(lat2*rad)*Math.sin(dLam/2)**2;
  return 2*6_371_000*Math.asin(Math.min(1,Math.sqrt(a)));
}

export function insideCoverage(c:Centre,lat:number,lon:number){return distanceM(c.center_lat,c.center_lon,lat,lon)<=c.radius_m;}
