import { memo } from "react";

/**
 * Speedometer gauge component for the HUD
 * Shows current speed with a visual arc and required speed marker
 */
const Speedometer = memo(({ 
  currentSpeed = 0, 
  requiredSpeed = null, 
  maxSpeed = 30, // Max speed on gauge
  size = 80,
  isDanger = false 
}) => {
  // Calculate angles (180 degree arc, from left to right)
  const startAngle = -90; // Start at left (9 o'clock)
  const endAngle = 90;    // End at right (3 o'clock)
  const angleRange = endAngle - startAngle;
  
  // Current speed angle
  const speedPercent = Math.min(currentSpeed / maxSpeed, 1);
  const speedAngle = startAngle + (speedPercent * angleRange);
  
  // Required speed angle (if provided)
  const requiredPercent = requiredSpeed ? Math.min(requiredSpeed / maxSpeed, 1) : null;
  const requiredAngle = requiredPercent ? startAngle + (requiredPercent * angleRange) : null;
  
  const center = size / 2;
  const radius = (size / 2) - 8;
  const innerRadius = radius - 6;
  
  // Helper to convert angle to coordinates
  const angleToCoord = (angle, r) => {
    const rad = (angle * Math.PI) / 180;
    return {
      x: center + r * Math.cos(rad),
      y: center + r * Math.sin(rad)
    };
  };
  
  // Create arc path
  const createArc = (startAng, endAng, r) => {
    const start = angleToCoord(startAng, r);
    const end = angleToCoord(endAng, r);
    const largeArc = endAng - startAng > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  };
  
  // Tick marks
  const ticks = [0, 10, 20, 30];
  
  return (
    <div className="relative" style={{ width: size, height: size / 2 + 12 }}>
      <svg width={size} height={size / 2 + 12} viewBox={`0 0 ${size} ${size / 2 + 12}`}>
        {/* Background arc */}
        <path
          d={createArc(startAngle, endAngle, radius)}
          fill="none"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth="6"
          strokeLinecap="round"
        />
        
        {/* Danger zone (above required speed) - only if required speed exists */}
        {requiredAngle && (
          <path
            d={createArc(requiredAngle, endAngle, radius)}
            fill="none"
            stroke="rgba(239,68,68,0.3)"
            strokeWidth="6"
            strokeLinecap="round"
          />
        )}
        
        {/* Safe zone (below required speed) */}
        {requiredAngle && (
          <path
            d={createArc(startAngle, requiredAngle, radius)}
            fill="none"
            stroke="rgba(34,197,94,0.2)"
            strokeWidth="6"
            strokeLinecap="round"
          />
        )}
        
        {/* Current speed arc */}
        <path
          d={createArc(startAngle, speedAngle, radius)}
          fill="none"
          stroke={isDanger ? "#ef4444" : "#06b6d4"}
          strokeWidth="6"
          strokeLinecap="round"
          style={{
            filter: `drop-shadow(0 0 6px ${isDanger ? 'rgba(239,68,68,0.5)' : 'rgba(6,182,212,0.5)'})`
          }}
        />
        
        {/* Required speed marker */}
        {requiredAngle && (
          <>
            {/* Marker line */}
            <line
              x1={angleToCoord(requiredAngle, innerRadius - 4).x}
              y1={angleToCoord(requiredAngle, innerRadius - 4).y}
              x2={angleToCoord(requiredAngle, radius + 4).x}
              y2={angleToCoord(requiredAngle, radius + 4).y}
              stroke={isDanger ? "#ef4444" : "#22c55e"}
              strokeWidth="2"
              strokeLinecap="round"
            />
          </>
        )}
        
        {/* Tick marks */}
        {ticks.map((tick) => {
          const tickPercent = tick / maxSpeed;
          const tickAngle = startAngle + (tickPercent * angleRange);
          const outer = angleToCoord(tickAngle, radius + 2);
          const inner = angleToCoord(tickAngle, radius - 3);
          return (
            <g key={tick}>
              <line
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                stroke="rgba(255,255,255,0.3)"
                strokeWidth="1"
              />
              <text
                x={angleToCoord(tickAngle, radius - 12).x}
                y={angleToCoord(tickAngle, radius - 12).y}
                fill="rgba(255,255,255,0.4)"
                fontSize="7"
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {tick}
              </text>
            </g>
          );
        })}
        
        {/* Center speed display */}
        <text
          x={center}
          y={center + 2}
          fill={isDanger ? "#ef4444" : "#06b6d4"}
          fontSize="18"
          fontWeight="bold"
          fontFamily="JetBrains Mono, monospace"
          textAnchor="middle"
          dominantBaseline="middle"
          style={{
            filter: `drop-shadow(0 0 4px ${isDanger ? 'rgba(239,68,68,0.5)' : 'rgba(6,182,212,0.3)'})`
          }}
        >
          {currentSpeed.toFixed(0)}
        </text>
        
        {/* MPH label */}
        <text
          x={center}
          y={center + 14}
          fill="rgba(255,255,255,0.5)"
          fontSize="7"
          fontFamily="Rajdhani, sans-serif"
          textAnchor="middle"
          letterSpacing="1"
        >
          MPH
        </text>
      </svg>
      
      {/* Required speed label */}
      {requiredSpeed && (
        <div 
          className={`absolute -bottom-1 left-1/2 -translate-x-1/2 text-[8px] font-mono ${isDanger ? 'text-red-400' : 'text-green-400'}`}
        >
          NEED {requiredSpeed.toFixed(0)}
        </div>
      )}
    </div>
  );
});

Speedometer.displayName = 'Speedometer';

export default Speedometer;
